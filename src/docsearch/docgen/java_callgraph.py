"""Call-graph edge extraction for parsed Java repositories.

Builds the ``(caller, callee)`` edges that populate :class:`Module.edges`
(see :mod:`docsearch.search.model`). Edges connect *entity* qualified names
using the same convention the Java parser emits
(:mod:`docsearch.docgen.java_parser`):

    * class            -> "ClassName"
    * method            -> "ClassName.methodName"
    * Java constructor   -> "ClassName constructor"

The extractor re-parses each file with the shared ``tree-sitter-java`` grammar
and walks its tree, tracking the enclosing type so every callable's caller
qualname is known exactly. Inside each callable body it runs tree-sitter
``query()`` for ``method_invocation`` and ``object_creation_expression`` nodes
and resolves each to an internal entity with best-effort heuristics.

Resolution is intentionally conservative: a call we cannot map to a *known*
qualname is dropped. The bi-level search has runtime implicit-edge discovery as
a safety net, so a missed edge costs far less than a wrong one. Nothing here
raises on an unexpected node shape; odd nodes are skipped.

Resolution rules implemented (best-effort, internal-only):

    * bare ``name(...)``  -> ``Class.name`` of the enclosing class, else a
      same-package class ``Other.name`` (a class sharing the caller's source
      directory), else dropped.
    * ``this.name(...)`` / ``super.name(...)`` -> ``Class.name`` of the
      enclosing class.
    * ``Type.name(...)`` (object is a simple type identifier) -> ``Type.name``
      if known, else the class entity ``Type`` if that is the only known match.
    * ``new Type(...)`` -> ``Type constructor`` if known, else the class entity
      ``Type`` if known.
    * A call/creation that resolves only to a class name (no matching member)
      maps to that class entity, so edges still land on the type.
    * Chained / field-access receivers (``a.b.c.name()``, ``foo().bar()``) are
      not statically resolvable here and are dropped.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from docsearch.docgen.models import FileStructure

# tree-sitter node types that introduce a documentable type (mirrors the parser).
_TYPE_DECL = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
_CALLABLE = {"method_declaration", "constructor_declaration"}

# Cached grammar/parser (grammar load is not free; reuse across files).
_LANGUAGE = None
_PARSER = None


def _get_language_and_parser():
    """Lazy-build the tree-sitter Java language + parser, or return ``(None, None)``.

    Mirrors :func:`docsearch.docgen.java_parser._get_parser` but also keeps the
    ``Language`` handle, which queries need. Never raises: if the grammar is not
    installed we degrade to "no edges" rather than crash the pipeline.
    """
    global _LANGUAGE, _PARSER
    if _PARSER is not None:
        return _LANGUAGE, _PARSER
    try:
        import tree_sitter_java as tsjava
        from tree_sitter import Language, Parser
    except ImportError:  # pragma: no cover - exercised only when missing
        return None, None
    try:
        language = Language(tsjava.language())
        try:
            parser = Parser(language)
        except TypeError:  # older tree-sitter API
            parser = Parser()
            parser.set_language(language)
    except Exception:  # pragma: no cover - defensive
        return None, None
    _LANGUAGE, _PARSER = language, parser
    return _LANGUAGE, _PARSER


def _text(src: bytes, node) -> str:
    """Decode the exact source slice spanned by a node."""
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _type_name(type_node, src: bytes) -> str:
    """Simple name of a type-declaration node (class/interface/enum/record)."""
    nm = type_node.child_by_field_name("name")
    return _text(src, nm) if nm is not None else ""


def _package_dir(file_path: str) -> str:
    """Directory portion of a file path, used as a same-package key.

    Java entity qualnames carry no package, so we approximate "same package"
    as "same source directory", which holds for conventionally laid-out repos.
    """
    p = file_path.replace("\\", "/")
    return p.rsplit("/", 1)[0] if "/" in p else ""


def _invocations(language, cursor_factory, body_node):
    """Yield ``method_invocation`` / ``object_creation_expression`` nodes in a body.

    Uses a tree-sitter query against the grammar. Never raises: a query error
    yields nothing.
    """
    try:
        from tree_sitter import Query, QueryCursor

        query = Query(
            language,
            "[(method_invocation) (object_creation_expression)] @call",
        )
        captures = QueryCursor(query).captures(body_node)
    except Exception:  # pragma: no cover - older API / query failure
        # Fallback: manual descent (robust, dependency-light).
        yield from _walk_invocations(body_node)
        return
    for nodes in captures.values():
        for node in nodes:
            yield node


def _walk_invocations(node):
    """Recursive descent fallback yielding invocation/creation nodes."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in ("method_invocation", "object_creation_expression"):
            yield cur
        stack.extend(cur.named_children)


def _register_callables(
    root,
    src: bytes,
    qualnames: Set[str],
) -> List[Tuple[str, object]]:
    """Walk the tree, returning ``(caller_qualname, body_node)`` for each callable.

    Tracks the enclosing type so each method/constructor's caller qualname is
    derived exactly. Only callables whose qualname is a known entity are kept.
    """
    out: List[Tuple[str, object]] = []
    # Stack of enclosing simple type names.
    stack = [(root, None)]  # (node, enclosing_type_name)
    while stack:
        node, enclosing = stack.pop()
        for child in node.named_children:
            if child.type in _TYPE_DECL:
                type_name = _type_name(child, src) or enclosing
                body = child.child_by_field_name("body")
                if body is not None:
                    stack.append((body, type_name))
            elif child.type in _CALLABLE and enclosing:
                caller = _callable_qualname(child, src, enclosing)
                if caller in qualnames:
                    body = child.child_by_field_name("body")
                    if body is not None:
                        out.append((caller, body))
                # A callable cannot contain a nested type, so no further descent.
            else:
                # Descend through wrappers (enum_body_declarations, etc.).
                stack.append((child, enclosing))
    return out


def _callable_qualname(node, src: bytes, class_name: str) -> str:
    """Qualname for a method/constructor node within ``class_name``."""
    if node.type == "constructor_declaration":
        return f"{class_name} constructor"
    nm = node.child_by_field_name("name")
    method = _text(src, nm) if nm is not None else ""
    return f"{class_name}.{method}"


def _resolve_invocation(
    node,
    src: bytes,
    caller_class: str,
    package_classes: Set[str],
    qualnames: Set[str],
    methods_by_name: Dict[str, List[str]],
) -> Optional[str]:
    """Resolve one invocation/creation node to a known internal qualname, or None."""
    if node.type == "object_creation_expression":
        type_node = node.child_by_field_name("type")
        if type_node is None:
            return None
        type_name = _simple_type(_text(src, type_node))
        if not type_name:
            return None
        ctor = f"{type_name} constructor"
        if ctor in qualnames:
            return ctor
        if type_name in qualnames:
            return type_name  # land on the class entity
        return None

    # method_invocation
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    method = _text(src, name_node)
    obj = node.child_by_field_name("object")

    if obj is None:
        # bare name(...) -> same class first, then a unique same-package class.
        same = f"{caller_class}.{method}"
        if same in qualnames:
            return same
        candidates = [
            q for q in methods_by_name.get(method, [])
            if q.split(".", 1)[0] in package_classes
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    if obj.type in ("this", "super"):
        # this.m() / super.m() -> enclosing class method.
        same = f"{caller_class}.{method}"
        return same if same in qualnames else None

    if obj.type == "identifier":
        # Type.m() — only a simple identifier is statically resolvable here.
        base = _text(src, obj)
        target = f"{base}.{method}"
        if target in qualnames:
            return target
        if base in qualnames:
            return base  # call lands on the class entity
        return None

    # Chained / field-access / array receivers are not statically resolvable.
    return None


def _simple_type(text: str) -> str:
    """Strip generics / array / package qualifier to a simple type name.

    ``java.util.List<String>[]`` -> ``List``; ``Foo<Bar>`` -> ``Foo``;
    ``a.b.C`` -> ``C``. Returns ``""`` if nothing usable remains.
    """
    t = text.split("<", 1)[0]
    t = t.split("[", 1)[0]
    t = t.strip()
    if "." in t:
        t = t.rsplit(".", 1)[-1]
    return t.strip()


def call_edges(
    file_structures: List[FileStructure],
    qualnames: Set[str],
) -> Set[Tuple[str, str]]:
    """Extract internal ``(caller, callee)`` call edges from parsed Java files.

    Args:
        file_structures: Parsed :class:`FileStructure` objects for the repo.
        qualnames: The set of known entity qualified names. Only edges whose
            both endpoints are in this set are returned (internal-only).

    Returns:
        A set of ``(caller_qualname, callee_qualname)`` pairs. Best-effort:
        statically unresolvable calls are dropped, and the function never
        raises (a parse/query failure for one file just yields no edges for it).
    """
    language, parser = _get_language_and_parser()
    if parser is None:
        return set()

    qualnames = set(qualnames)

    # Map simple method name -> list of qualnames declaring it, for same-package
    # bare-call resolution.
    methods_by_name: Dict[str, List[str]] = {}
    for q in qualnames:
        if "." in q and " constructor" not in q:
            methods_by_name.setdefault(q.rsplit(".", 1)[-1], []).append(q)

    # Map source directory -> set of class names declared there (same-package set).
    classes_by_dir: Dict[str, Set[str]] = {}
    for fs in file_structures:
        if (fs.language or "").lower() != "java":
            continue
        directory = _package_dir(fs.file_path)
        bucket = classes_by_dir.setdefault(directory, set())
        for obj in fs.objects:
            if obj.obj_type == "class":
                bucket.add(obj.qualified_name)

    edges: Set[Tuple[str, str]] = set()

    for fs in file_structures:
        if (fs.language or "").lower() != "java":
            continue
        try:
            src = (fs.source_code or "").encode("utf-8")
            tree = parser.parse(src)
            root = tree.root_node
        except Exception:  # pragma: no cover - defensive
            continue

        package_classes = classes_by_dir.get(_package_dir(fs.file_path), set())

        for caller, body in _register_callables(root, src, qualnames):
            caller_class = (
                caller.split(" constructor", 1)[0]
                if caller.endswith(" constructor")
                else caller.rsplit(".", 1)[0]
            )
            for inv in _invocations(language, None, body):
                try:
                    callee = _resolve_invocation(
                        inv,
                        src,
                        caller_class,
                        package_classes,
                        qualnames,
                        methods_by_name,
                    )
                except Exception:  # pragma: no cover - never raise on odd nodes
                    callee = None
                if callee and callee != caller:
                    edges.add((caller, callee))

    return edges
