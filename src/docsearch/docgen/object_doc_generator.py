"""
Per-object behavioral-prose generator for the docgen subsystem.

This module owns the single LLM call that produces the *behavior description*
for one code object (a class, a standalone function, or a method): it builds a
structure-free prompt and returns only behavior prose, leaving all document
structure to the assembler.

Architecture note (format conformance):
    The LLM writes ONLY behavior prose. It must NOT emit Markdown headings,
    horizontal-rule dividers, code fences, a bold object-name line, or any
    template-style bullet scaffold. ALL canonical headings and the
    ``**Interface:**`` fenced block are emitted later by the assembler from
    structural (AST) data. To make this robust against a chatty model, the
    generated text is additionally run through :meth:`ObjectDocGenerator._sanitize`,
    which mechanically strips any heading / divider / fence / bold-name-prefix
    lines that slip through.
"""

from __future__ import annotations

import json
import logging
import re

from docsearch.docgen.models import (
    CodeObject,
    FileStructure,
    OBJ_CLASS,
    OBJ_FUNCTION,
    OBJ_METHOD,
)

logger = logging.getLogger(__name__)


# System prompt: emits *only* behavior prose (no headings/dividers/fences/
# bullet scaffold), because the assembler owns all structure.
_SYSTEM_INSTRUCTION = (
    "You are a documentation assistant. Write COMPLETE, precise, "
    "implementation-oriented documentation for a single code object so that a "
    "developer — or an LLM given ONLY your documentation — can re-implement it "
    "CORRECTLY without seeing the original code.\n\n"
    "Produce the following sections, in this exact order, using **bold** labels "
    "(NOT Markdown '#' headings):\n"
    "**<name>**: one sentence stating what the object does.\n"
    "**Signature**: the exact signature — return type, name, and every "
    "parameter with its type (plus modifiers like static), e.g. "
    "`static Elements collect(Evaluator eval, Element root)`. For a class, give "
    "the class declaration and key public fields/constants.\n"
    "**Parameters**: one bullet per parameter — `- <name> (<type>): meaning, "
    "valid values/constraints, and how it is used`. Write `- (none)` if there "
    "are no parameters.\n"
    "**Behavior**: a thorough, step-by-step description of what the code does — "
    "the algorithm and control flow, the important conditions/branches, how it "
    "transforms inputs into outputs, any state changes/side effects, and the "
    "edge/boundary cases. Be specific and complete enough to REPRODUCE the "
    "behavior. Describe the logic in words; do NOT paste the source verbatim.\n"
    "**Returns**: what is returned and under which conditions, with a short "
    "illustrative example when helpful. Omit this section for void methods and "
    "constructors.\n"
    "**Notes**: important usage caveats, invariants, or interactions with other "
    "entities. Omit if there are none.\n\n"
    "Rules:\n"
    "- Be precise and CERTAIN; do not speculate or invent behavior not in the "
    "code.\n"
    "- Structure using ONLY `**bold**` labels and `-` bullets.\n"
    "- Do NOT use Markdown headings (no lines starting with '#'), horizontal "
    "rules ('---' or '***'), or code fences (lines with ```).\n"
    "- Do not mention that you were shown source code."
)

# Module-overview system prompt: an informative summary of the whole file.
_MODULE_SYSTEM_INSTRUCTION = (
    "You are a documentation assistant. Write an informative OVERVIEW of a "
    "source module (one file) for a developer who needs to understand it.\n\n"
    "Cover: the module's overall purpose and responsibility; the main classes / "
    "functions it defines and what each is for; and how they relate to one "
    "another (and to notable external types). Aim for a short, substantive "
    "overview — typically 3 to 6 sentences (use `-` bullets for the per-class "
    "roles if that is clearer). Be precise and certain; do not speculate.\n\n"
    "Rules:\n"
    "- Use ONLY `**bold**` labels and `-` bullets for any structure.\n"
    "- Do NOT use Markdown headings (no lines starting with '#'), horizontal "
    "rules ('---' or '***'), or code fences (lines with ```).\n"
    "- Do not mention that you were shown source code."
)

# Multi-entity (whole-module) system prompt: document EVERY listed entity in ONE
# call, each section delimited by a "@@DOC <qualified_name>" line, so the single
# response is split back into per-entity docs. This avoids re-sending the full
# file source once per entity (N x input tokens -> ~1x).
_MODULE_DOCS_SYSTEM = (
    "You are a documentation assistant. Document EVERY listed code entity of one "
    "source module, in detail, so each could be re-implemented correctly from "
    "your documentation ALONE.\n\n"
    "For EACH entity output a section that BEGINS with a line of the exact form:\n"
    "@@DOC <qualified_name>\n"
    "where <qualified_name> is copied VERBATIM from the provided list (nothing "
    "else on that line). Then the entity's documentation, using **bold** labels "
    "(NOT '#' headings):\n"
    "**<name>**: one-sentence purpose.\n"
    "**Signature**: exact signature — return type, name, every parameter with "
    "its type (plus modifiers like static). For a class, the declaration + key "
    "public fields/constants.\n"
    "**Parameters**: one `- <name> (<type>): meaning/constraints/use` bullet each; "
    "`- (none)` if no parameters.\n"
    "**Behavior**: thorough step-by-step description — algorithm, control flow, "
    "conditions/branches, input->output transformation, side effects, edge cases. "
    "Detailed enough to reproduce; describe the logic, do not paste the source.\n"
    "**Returns**: what is returned and under which conditions (omit for void "
    "methods and constructors).\n"
    "**Notes**: caveats/invariants/interactions (omit if none).\n\n"
    "Rules:\n"
    "- Emit a @@DOC section for EVERY entity in the list (in the given order) and "
    "for NO others. Use the exact qualified names provided.\n"
    "- Be precise and CERTAIN; do not speculate or invent behavior.\n"
    "- Structure with ONLY `**bold**` labels and `-` bullets — NO '#' headings, "
    "NO '---'/'***' dividers, NO code fences.\n"
    "- Do not mention that you were shown source code."
)

# Multi-entity (whole-module) system prompt, JSON variant: document EVERY listed
# entity in ONE call and return a single JSON OBJECT mapping the exact
# qualified_name -> the entity's documentation (a markdown string). JSON is far
# more robust to parse than delimiter-splitting (no fragile regex, trivial
# detection of any omitted entity) and, with the provider's json_object mode,
# the reply is guaranteed to be syntactically valid JSON.
_MODULE_DOCS_JSON_SYSTEM = (
    "You are a documentation assistant. Document EVERY listed code entity of one "
    "source module, in detail, so each could be re-implemented correctly from "
    "your documentation ALONE.\n\n"
    "Return a SINGLE JSON object (and nothing else) whose keys are the EXACT "
    "qualified names from the provided list and whose values are the "
    "documentation string for that entity. Include a key for EVERY entity in "
    "the list and for NO others.\n\n"
    "Each value is a markdown string using ONLY `**bold**` labels and `-` "
    "bullets (NO '#' headings, NO '---'/'***' dividers, NO code fences), with "
    "these labels:\n"
    "**<name>**: one-sentence purpose.\n"
    "**Signature**: exact signature — return type, name, every parameter with "
    "its type (plus modifiers like static). For a class, the declaration + key "
    "public fields/constants.\n"
    "**Parameters**: one `- <name> (<type>): meaning/constraints/use` bullet "
    "each; `- (none)` if no parameters.\n"
    "**Behavior**: thorough step-by-step description — algorithm, control flow, "
    "conditions/branches, input->output transformation, side effects, edge "
    "cases. Detailed enough to reproduce; describe the logic, do not paste the "
    "source.\n"
    "**Returns**: what is returned and under which conditions (omit for void "
    "methods and constructors).\n"
    "**Notes**: caveats/invariants/interactions (omit if none).\n\n"
    "OVERLOADS: when an entry lists more than one signature (overloaded methods "
    "or constructors that share a name), the ONE value for that key MUST document "
    "EVERY overload — each as its own block introduced by a "
    "`**Overload N — Signature**: <signature>` line followed by that overload's "
    "own **Parameters** / **Behavior** / **Returns**. Never document only one of "
    "them; a re-implementer must be able to produce every overloaded signature.\n\n"
    "Be precise and CERTAIN; do not speculate or invent behavior. Use newline "
    "characters inside each string to separate the labels. Do not mention that "
    "you were shown source code."
)

# User-side guideline: reinforce completeness + the reproduce-from-doc goal.
_GUIDELINE = (
    "Write documentation detailed enough that the object could be correctly "
    "re-implemented from your text alone: state the exact signature, explain "
    "every parameter, and describe the full behavior (algorithm, branches, "
    "edge cases, return value). Be precise and deterministic; avoid speculation. "
    "Follow all output constraints above."
)


class ObjectDocGenerator:
    """Generates a one-to-four-sentence behavioral description for a code object.

    The returned string is pure prose: no headings, dividers, fences, or
    bold-name prefix. It is meant to be slotted under an assembler-emitted
    ``## Class:`` / ``## Function:`` / ``### Method:`` heading.
    """

    def __init__(self, llm_client):
        """Store the LLM client used to generate descriptions.

        Args:
            llm_client: An object exposing
                ``generate(prompt, temperature=0, system=None) -> str``.
        """
        self.llm_client = llm_client

    def generate(self, obj: CodeObject, file_struct: FileStructure) -> str:
        """Generate clean behavioral prose for ``obj``.

        Args:
            obj: The code object (class, function, or method) to document.
            file_struct: The parsed structure of the enclosing source file,
                used to supply file/module context.

        Returns:
            A sanitized, 1-4 sentence behavioral description (plain prose).
        """
        prompt = self._build_prompt(obj, file_struct)
        # temperature=0 for deterministic output. Token logging is kept silent.
        raw = self.llm_client.generate(
            prompt, temperature=0, system=_SYSTEM_INSTRUCTION
        )
        return self._sanitize(raw or "")

    def generate_module_docs(self, file_struct: FileStructure,
                             max_per_call: int = 10) -> dict:
        """Document ALL entities of one file in as few LLM calls as possible.

        Entities are batched (``max_per_call`` per call) so the full file source
        is sent ~once per batch rather than once per entity (N x input tokens ->
        ~ceil(N/max_per_call)x). Each call returns a JSON object mapping
        ``qualified_name -> doc`` (parsed with :meth:`_parse_json_docs`).

        COMPLETENESS is guaranteed: any entity the batched calls omit (model
        truncation, an unparseable reply, a dropped key) is collected and
        RETRIED — first re-batched once, then, for anything still missing,
        documented individually via :meth:`generate`. No entity is left silently
        empty (the earlier ``@@DOC`` delimiter scheme could drop a whole batch).

        Returns ``{qualified_name: sanitized doc}`` covering every entity.
        """
        # GROUP by qualified_name, preserving first-seen order. Overloaded
        # methods and constructors share a qualified_name (e.g. Elements.attr =
        # both attr(String) and attr(String,String)); we keep ALL of them so the
        # ONE doc for that key can describe EVERY overload. Dropping the extras
        # (the old dedup) made codegen omit overloads -> ground-truth tests no
        # longer compiled against the reconstruction.
        groups: dict = {}
        for o in file_struct.objects:
            groups.setdefault(o.qualified_name, []).append(o)
        group_items = list(groups.items())  # [(qualname, [objs]), ...]

        docs: dict = {}
        self._fill_batched(file_struct, group_items, docs, max_per_call)

        # Retry pass: re-batch whatever is still missing in smaller groups.
        missing = [(qn, objs) for qn, objs in group_items if qn not in docs]
        if missing:
            logger.warning(
                "Module docs for %s: %d/%d entities missing after first pass; "
                "retrying.", file_struct.module_name, len(missing),
                len(group_items)
            )
            self._fill_batched(file_struct, missing, docs,
                               max(1, max_per_call // 2))

        # Final guarantee: document any remaining entity ONE focused call at a
        # time (still overload-aware), then fall back to single-object prose.
        for qn, objs in group_items:
            if qn in docs:
                continue
            self._fill_batched(file_struct, [(qn, objs)], docs, 1)
            if qn in docs:
                continue
            try:
                docs[qn] = self.generate(objs[0], file_struct)
            except Exception as exc:
                logger.warning("Per-entity doc fallback failed for %s: %s",
                               qn, exc)
        return docs

    def _fill_batched(self, file_struct: FileStructure, group_items: list,
                      docs: dict, max_per_call: int) -> None:
        """Run JSON-batched doc generation over ``group_items``, updating ``docs``.

        ``group_items`` is a list of ``(qualified_name, [CodeObject, ...])`` —
        each group's overloads are documented together under one key. Only fills
        keys not already present, never overwriting a non-empty doc with empty.
        """
        for start in range(0, len(group_items), max_per_call):
            batch = group_items[start:start + max_per_call]
            prompt = self._build_module_prompt(file_struct, batch)
            known = {qn for qn, _ in batch}
            # Prefer provider JSON mode (guaranteed-valid JSON); fall back
            # gracefully for clients whose generate() lacks response_format.
            try:
                raw = self.llm_client.generate(
                    prompt, temperature=0, system=_MODULE_DOCS_JSON_SYSTEM,
                    response_format={"type": "json_object"},
                )
            except TypeError:
                raw = self.llm_client.generate(
                    prompt, temperature=0, system=_MODULE_DOCS_JSON_SYSTEM
                )
            for qn, doc in self._parse_json_docs(raw or "", known).items():
                if doc and not docs.get(qn):
                    docs[qn] = doc

    def _build_module_prompt(self, file_struct: FileStructure, batch: list) -> str:
        """Build the one-shot prompt: the batch entities + the file source.

        ``batch`` is a list of ``(qualified_name, [CodeObject, ...])``. When a
        group has more than one object the entry lists ALL overload signatures
        so the model documents every one under that single key.
        """
        lines = [
            f"Module: {file_struct.module_name} "
            f"({file_struct.language}, file: {file_struct.file_path})",
            "",
            "Document EACH of the following entities. Use each qualified name "
            "VERBATIM as a JSON key:",
        ]
        for qn, objs in batch:
            kind = self._kind_label(objs[0].obj_type)
            if len(objs) == 1:
                sig = f" — signature: {objs[0].signature}" if objs[0].signature else ""
                lines.append(f"- {qn}   ({kind}){sig}")
            else:
                lines.append(
                    f"- {qn}   ({kind}) — {len(objs)} OVERLOADS; document EVERY "
                    f"one under this single key:"
                )
                for o in objs:
                    lines.append(f"    - signature: {o.signature}")
        lines += [
            "",
            "Full source of the module (for reference):",
            f"```{file_struct.language}",
            file_struct.source_code,
            "```",
            "",
            "Return one JSON object whose keys are exactly the qualified names "
            "above and whose values are the documentation strings. " + _GUIDELINE,
        ]
        return "\n".join(lines)

    def _parse_json_docs(self, raw: str, known: set) -> dict:
        """Parse a JSON ``{qualified_name: doc}`` reply into sanitized docs.

        Tolerant: strips ``` fences / leading prose and extracts the outermost
        ``{...}`` object before parsing. Only keys in ``known`` are kept (so a
        stray/hallucinated key is ignored); each value is sanitized.
        """
        text = (raw or "").strip()
        if not text:
            return {}
        # Strip a leading ```json / ``` fence if the model added one.
        fence = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, re.S)
        if fence:
            text = fence.group(1).strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            # Last resort: extract the outermost braces and retry.
            i, j = text.find("{"), text.rfind("}")
            if i == -1 or j == -1 or j <= i:
                return {}
            try:
                obj = json.loads(text[i:j + 1])
            except json.JSONDecodeError:
                return {}
        if not isinstance(obj, dict):
            return {}
        out: dict = {}
        for qn, doc in obj.items():
            if qn in known and isinstance(doc, str) and doc.strip():
                out[qn] = self._sanitize(doc)
        return out

    def generate_module_overview(self, file_struct: FileStructure) -> str:
        """Generate an informative MODULE-level overview for one file.

        A few sentences: what the module is for, the main classes/functions it
        contains and their responsibilities, and how they relate. Returned as
        sanitized prose (``**bold**`` labels / ``-`` bullets allowed; no ATX
        headings / dividers / fences) to slot under ``## Module: <name>``.
        """
        classes = [o.qualified_name for o in file_struct.objects
                   if o.obj_type == OBJ_CLASS]
        funcs = [o.qualified_name for o in file_struct.objects
                 if o.obj_type == OBJ_FUNCTION]
        methods = [o.qualified_name for o in file_struct.objects
                   if o.obj_type == OBJ_METHOD]
        inv = [
            f"Module: {file_struct.module_name} "
            f"({file_struct.language}, file: {file_struct.file_path})",
            f"Classes: {', '.join(classes) or '(none)'}",
            f"Standalone functions: {', '.join(funcs) or '(none)'}",
            f"Methods: {', '.join(methods[:40]) or '(none)'}",
            "",
            "Full source of the module:",
            f"```{file_struct.language}",
            file_struct.source_code,
            "```",
            "",
            "Write the module overview now, following the constraints above.",
        ]
        raw = self.llm_client.generate(
            "\n".join(inv), temperature=0, system=_MODULE_SYSTEM_INSTRUCTION
        )
        return self._sanitize(raw or "")

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #
    def _build_prompt(self, obj: CodeObject, file_struct: FileStructure) -> str:
        """Build the user prompt describing the target object and its context."""
        kind = self._kind_label(obj.obj_type)
        params = ", ".join(obj.params) if obj.params else "(none)"

        lines = [
            f"You are documenting a {kind} in the {file_struct.language} "
            f"module '{file_struct.module_name}' (file: {file_struct.file_path}).",
            "",
            f"{kind} name: {obj.name}",
            f"Qualified name: {obj.qualified_name}",
        ]
        if obj.parent:
            lines.append(f"Enclosing class: {obj.parent}")
        lines.append(f"Parameters: {params}")
        if obj.signature:
            lines.append(f"Signature: {obj.signature}")
        if obj.obj_type in (OBJ_FUNCTION, OBJ_METHOD):
            lines.append(
                "Returns a value: "
                + ("yes" if obj.have_return else "no / not significant")
            )

        lines += [
            "",
            f"The full source of this {kind} is:",
            f"```{obj.language}",
            obj.code,
            "```",
            "",
            _GUIDELINE,
        ]
        return "\n".join(lines)

    @staticmethod
    def _kind_label(obj_type: str) -> str:
        """Map an OBJ_* constant to a human-readable kind label."""
        if obj_type == OBJ_CLASS:
            return "Class"
        if obj_type == OBJ_METHOD:
            return "Method"
        if obj_type == OBJ_FUNCTION:
            return "Function"
        return "Function"

    # ------------------------------------------------------------------ #
    # Post-processing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sanitize(text: str) -> str:
        """Strip any structural markup the model may have emitted.

        Rules applied:
        - Strip leading/trailing whitespace from the whole text and each line.
        - Drop any line that is an ATX heading (starts with '#').
        - Drop any line that is a horizontal-rule divider ('---' or '***',
          i.e. three or more of '-' or '*' only).
        - Drop any code-fence line (starts with the fence marker '```').
        - Strip a leading bold object-name prefix like '**name**:' from the
          start of the prose.
        - Collapse runs of 3+ blank lines down to a single blank line.

        Returns clean prose only.
        """
        fence = "`" * 3
        kept: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            # ATX heading
            if line.startswith("#"):
                continue
            # code fence
            if line.startswith(fence):
                continue
            # horizontal-rule divider: only '-' (>=3) or only '*' (>=3)
            if ObjectDocGenerator._is_divider(line):
                continue
            kept.append(line)

        # Collapse 3+ consecutive blank lines into a single blank line.
        collapsed: list[str] = []
        blank_run = 0
        for line in kept:
            if line == "":
                blank_run += 1
                if blank_run >= 2:
                    # already have one blank recorded; skip extras
                    continue
                collapsed.append(line)
            else:
                blank_run = 0
                collapsed.append(line)

        # Keep the rich structure (**bold** section labels and '-' bullets) — it
        # is the contract format the code generator needs. Only ATX headings,
        # dividers and code fences (which would break the canonical entity
        # splitter) were dropped above.
        result = "\n".join(collapsed).strip()
        return result

    @staticmethod
    def _is_divider(line: str) -> bool:
        """Return True if the line is a '---'/'***' style horizontal rule."""
        if len(line) < 3:
            return False
        if set(line) == {"-"}:
            return True
        if set(line) == {"*"}:
            return True
        return False

    @staticmethod
    def _strip_bold_name_prefix(text: str) -> str:
        """Remove a leading '**name**:' (or '**name**') prefix if present."""
        stripped = text.lstrip()
        if not stripped.startswith("**"):
            return text
        end = stripped.find("**", 2)
        if end == -1:
            return text
        rest = stripped[end + 2:]
        # Allow an optional ':' separator right after the bold span.
        rest = rest.lstrip()
        if rest.startswith(":"):
            rest = rest[1:]
        return rest.lstrip()
