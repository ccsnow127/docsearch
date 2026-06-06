"""Java source parser for the documentation-generation subsystem (docgen).

Parses a single Java source file into the shared :class:`FileStructure` model
using ``tree-sitter`` with the ``tree-sitter-java`` grammar. The public API
mirrors :mod:`python_parser` exactly so callers can dispatch on language
without special-casing.

Why tree-sitter (and not a pure-Python Java grammar): real-world Java repos use
syntax that older pure-Python parsers do not fully cover (pattern ``instanceof``,
switch expressions, records, sealed types, text blocks, …), and even plain Java 8
code exposes gaps. tree-sitter's Java grammar tracks the modern language and is
*error-tolerant*: a file with a localized syntax error still yields a usable
parse tree, so we can extract partial structure instead of dropping the whole
file. It also provides exact start/end line ranges for every node.

This parser intentionally produces *structural* data only (signatures, field
declarations, line ranges, recoverable source text). The behavioural prose and
all canonical-doc headings / ``**Interface:**`` blocks are emitted later by the
assembler from this structural data, never by the parser or the LLM.

Conventions (preserved from the project's existing Java baseline format, see
``dataset/java/docs/baseline_doc_java.md``):
  * The first top-level type is treated as the *module* (``module_name``).
  * Its nested types become the documented classes. Additional top-level types
    are documented too. If the top-level type has no nested types, the
    top-level type itself is the single documented class.
  * The top-level type is ALSO documented as a class when it declares methods or
    constructors of its own (so a class that mixes direct methods with a nested
    helper never loses its methods); a pure container type that only holds
    nested types stays the module and is not emitted as a class.
  * Interfaces, enums and records are treated like classes for documentation.
  * Methods become ``OBJ_METHOD`` objects (``ClassName.methodName``);
    constructors become ``OBJ_METHOD`` objects with ``is_constructor=True`` and
    qualified name ``"ClassName constructor"``.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from docsearch.docgen.models import (
    CodeObject,
    FileStructure,
    OBJ_CLASS,
    OBJ_METHOD,
)

# tree-sitter node types that declare a documentable type.
_TYPE_DECL = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
_CALLABLE = {"method_declaration", "constructor_declaration"}

# Cached parser (grammar load is not free; reuse across files).
_PARSER = None


def _get_parser():
    """Lazy-build a tree-sitter Java parser, raising a clear error if missing."""
    global _PARSER
    if _PARSER is not None:
        return _PARSER
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError as exc:  # pragma: no cover - exercised only when missing
        raise ImportError(
            "tree-sitter and tree-sitter-java are required to parse Java sources. "
            "Install them with: pip install tree-sitter tree-sitter-java"
        ) from exc

    language = Language(tsjava.language())
    try:
        parser = Parser(language)
    except TypeError:  # older tree-sitter API
        parser = Parser()
        parser.set_language(language)
    _PARSER = parser
    return _PARSER


def _module_name_from_path(file_path: str) -> str:
    """Derive a fallback module name from the file path (basename, no ext)."""
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.endswith(".java"):
        name = name[: -len(".java")]
    return name or "module"


def _text(src: bytes, node) -> str:
    """Decode the exact source slice spanned by a node."""
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _name(src: bytes, node) -> str:
    nm = node.child_by_field_name("name")
    return _text(src, nm) if nm is not None else ""


def _start_line(node) -> int:
    return node.start_point[0] + 1


def _end_line(node) -> int:
    return node.end_point[0] + 1


def _collapse_ws(text: str) -> str:
    """Collapse all runs of whitespace (incl. newlines) to single spaces."""
    return " ".join(text.split())


def _type_body(type_node):
    """Return the body node of a type declaration (class/interface/enum/record)."""
    return type_node.child_by_field_name("body")


def _members(body):
    """Yield direct member nodes of a type body.

    Descends one level into ``enum_body_declarations`` so that methods/fields
    declared in an enum body are surfaced as direct members.
    """
    if body is None:
        return
    for child in body.named_children:
        if child.type == "enum_body_declarations":
            for sub in child.named_children:
                yield sub
        else:
            yield child


def _signature_text(node, src: bytes) -> str:
    """One-line signature: source from the node start up to its body / terminator.

    For a method/constructor with a body block, cut at the body start (drops the
    ``{ ... }``). For abstract/interface methods (no body) cut at the trailing
    ``;``. Whitespace and newlines are collapsed; a trailing ``{`` or ``;`` is
    removed.
    """
    body = node.child_by_field_name("body")
    if body is not None:
        raw = src[node.start_byte : body.start_byte]
    else:
        raw = src[node.start_byte : node.end_byte]
    sig = _collapse_ws(raw.decode("utf-8", errors="replace"))
    sig = sig.rstrip()
    while sig and sig[-1] in "{;":
        sig = sig[:-1].rstrip()
    return sig


def _class_signature_line(node, src: bytes) -> str:
    """Class/interface/enum declaration line, ending in `` {``.

    e.g. ``public static class Renko extends Instrument {``.
    """
    sig = _signature_text(node, src)
    return sig + " {"


def _param_name(param_node, src: bytes) -> Optional[str]:
    """Extract the declared name of a formal/spread/receiver parameter."""
    nm = param_node.child_by_field_name("name")
    if nm is not None:
        return _text(src, nm)
    # spread_parameter (varargs) and some shapes carry the name inside a
    # variable_declarator or as a bare identifier.
    for child in param_node.named_children:
        if child.type == "variable_declarator":
            inner = child.child_by_field_name("name") or child
            return _text(src, inner)
    for child in param_node.named_children:
        if child.type == "identifier":
            return _text(src, child)
    return None


def _param_names(callable_node, src: bytes) -> List[str]:
    params = callable_node.child_by_field_name("parameters")
    if params is None:
        return []
    names: List[str] = []
    for param in params.named_children:
        if param.type in ("formal_parameter", "spread_parameter"):
            name = _param_name(param, src)
            if name:
                names.append(name)
        # receiver_parameter (the explicit `this` receiver) carries no usable
        # argument name and is intentionally skipped.
    return names


def _method_has_return_value(method_node) -> bool:
    """Whether a method's declared return type is non-void."""
    rtype = method_node.child_by_field_name("type")
    if rtype is None:
        return False
    return rtype.type != "void_type"


def _field_text(field_node, src: bytes) -> str:
    """Verbatim, whitespace-collapsed text of a field declaration."""
    return _collapse_ws(_text(src, field_node))


def _build_member(member, class_name: str, src: bytes) -> CodeObject:
    """Build a CodeObject for a method or constructor declaration."""
    start = _start_line(member)
    end = _end_line(member)
    if member.type == "constructor_declaration":
        return CodeObject(
            obj_type=OBJ_METHOD,
            name=class_name,
            qualified_name=f"{class_name} constructor",
            parent=class_name,
            params=_param_names(member, src),
            signature=_signature_text(member, src),
            start_line=start,
            end_line=end,
            code=_text(src, member),
            language="java",
            is_constructor=True,
            have_return=False,
        )
    method_name = _name(src, member)
    return CodeObject(
        obj_type=OBJ_METHOD,
        name=method_name,
        qualified_name=f"{class_name}.{method_name}",
        parent=class_name,
        params=_param_names(member, src),
        signature=_signature_text(member, src),
        start_line=start,
        end_line=end,
        code=_text(src, member),
        language="java",
        is_constructor=False,
        have_return=_method_has_return_value(member),
    )


def _collect_class(type_node, src: bytes) -> Tuple[CodeObject, List[CodeObject]]:
    """Build the CodeObject for a type plus its method/constructor objects."""
    class_name = _name(src, type_node)
    body = _type_body(type_node)

    members: List[CodeObject] = []
    field_strings: List[str] = []
    for member in _members(body):
        if member.type in _CALLABLE:
            members.append(_build_member(member, class_name, src))
        elif member.type == "field_declaration":
            field_strings.append(_field_text(member, src))

    members.sort(key=lambda o: o.start_line)
    children = [m.qualified_name for m in members]
    # fields: declared field/constant lines only. The class signature is carried
    # on `signature` and emitted separately by the assembler, so it must NOT be
    # duplicated into `fields`.
    fields = field_strings

    class_obj = CodeObject(
        obj_type=OBJ_CLASS,
        name=class_name,
        qualified_name=class_name,
        parent=None,
        params=[],
        signature=_class_signature_line(type_node, src),
        start_line=_start_line(type_node),
        end_line=_end_line(type_node),
        code=_text(src, type_node),
        language="java",
        fields=fields,
        children=children,
    )
    return class_obj, members


def _nested_types(type_node) -> List:
    return [m for m in _members(_type_body(type_node)) if m.type in _TYPE_DECL]


def _direct_callables(type_node) -> List:
    return [m for m in _members(_type_body(type_node)) if m.type in _CALLABLE]


def parse_file(file_path: str, source_code: str) -> FileStructure:
    """Parse a single Java source file into a :class:`FileStructure`.

    Args:
        file_path: Path of the source (used for the module name); may be
            ``"<source>"`` for inline content.
        source_code: Full Java source text.

    Returns:
        A :class:`FileStructure` with ``objects`` sorted by ``start_line``.

    Raises:
        ImportError: If tree-sitter / tree-sitter-java are not installed.
        ValueError: If the source cannot be parsed at all.

    Note:
        tree-sitter is error-tolerant: a file with a localized syntax error
        still yields a usable tree, so partial structure is extracted rather
        than discarding the whole file.
    """
    parser = _get_parser()

    try:
        tree = parser.parse(source_code.encode("utf-8"))
        root = tree.root_node
    except Exception as exc:  # pragma: no cover - tree-sitter rarely raises
        raise ValueError(f"Failed to parse Java source {file_path!r}: {exc}") from exc

    src = source_code.encode("utf-8")

    top_types = [c for c in root.named_children if c.type in _TYPE_DECL]

    if top_types:
        module_name = _name(src, top_types[0]) or _module_name_from_path(file_path)
    else:
        module_name = _module_name_from_path(file_path)

    documented: List = []
    if top_types:
        outer = top_types[0]
        documented.extend(_nested_types(outer))
        documented.extend(top_types[1:])
        # Keep the outer type as a documented class when it has its own methods,
        # or when nothing else would be documented.
        if _direct_callables(outer) or not documented:
            documented = [outer] + documented

    objects: List[CodeObject] = []
    for type_node in documented:
        class_obj, members = _collect_class(type_node, src)
        objects.append(class_obj)
        objects.extend(members)

    objects.sort(key=lambda o: o.start_line)

    return FileStructure(
        file_path=file_path,
        module_name=module_name,
        language="java",
        source_code=source_code,
        objects=objects,
    )
