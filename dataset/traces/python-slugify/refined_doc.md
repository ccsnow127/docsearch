# python-slugify Baseline Documentation

## Module: slugify

**Purpose**: This module generates URL- and filename-friendly “slugs” from arbitrary text by normalizing Unicode, optionally decoding HTML character references, filtering disallowed characters, collapsing separators, removing stopwords, and optionally truncating the result.

**Key functions**
- **smart_truncate(string, max_length, word_boundary, separator, save_order)**: Trims a string to `max_length`, optionally respecting word boundaries based on `separator`; when `save_order` is true it stops at the first word that would exceed the limit rather than skipping ahead to later shorter words.
- **slugify(text, ..., allow_unicode)**: Produces the final slug by applying optional user `replacements`, quote handling, Unicode normalization (and ASCII transliteration via `unidecode` when `allow_unicode` is false), optional HTML entity/decimal/hex decoding, lowercasing, numeric comma cleanup, regex-based character filtering (defaulting to ASCII-only or Unicode-aware patterns), duplicate-separator collapsing, optional `stopwords` removal, and optional length limiting via `smart_truncate`.

**Relationships and external types**: `slugify` is the primary entry point and delegates truncation to `smart_truncate`; it relies on `re.Pattern`/regex substitution, `unicodedata.normalize`, `html.entities.name2codepoint` for named entity decoding, and `unidecode.unidecode` (or `text_unidecode` fallback) for transliteration when Unicode output is not allowed.

---

## Function: smart_truncate

```python
def smart_truncate(string: str, max_length: int=0, word_boundary: bool=False, separator: str=' ', save_order: bool=False) -> str
```

**smart_truncate**: Truncate a separator-delimited string to a maximum length, optionally respecting word boundaries and optionally preserving original word order constraints.

**Signature**: def smart_truncate(string: str, max_length: int = 0, word_boundary: bool = False, separator: str = ' ', save_order: bool = False) -> str

**Parameters**:
- string (str): Input string to truncate; treated as a sequence of tokens separated by `separator`.
- max_length (int): Maximum allowed length of the returned string; if 0 (or otherwise falsy), no truncation is performed.
- word_boundary (bool): If False, truncation may cut through words; if True, truncation attempts to cut only at `separator` boundaries using the token-based logic described below.
- separator (str): Separator used to strip leading/trailing separators and (when `word_boundary` is True) to split/join words. Treated literally as a string passed to `str.strip`, `str.split`, and concatenation (not a regex). Note: `str.strip(separator)` uses Python semantics (treats `separator` as a set of characters to strip, not a substring).
- save_order (bool): Only relevant when `word_boundary` is True; if True, once a word does not fit, stop immediately (do not try later words). If False, a word that does not fit may be skipped and later words may still be appended if they fit.

**Behavior**:
- **Strict scope / must-follow constraints (grading-critical)**:
- The submission/module must define **only** this single public function named `smart_truncate` with the exact signature above.
- Do **not** add any other top-level names (no helper functions, no classes, no constants such as `DEFAULT_SEPARATOR`, no aliases, no “slugify”, no `__all__`, etc.).
- Do **not** add any imports (standard library or third-party). This function must be implementable with Python built-ins only; the grader may fail if any imports or extra public symbols are present.
- Do not perform any I/O or side effects (no printing, logging, file/network access, environment access, randomness, etc.).
- **Normalization**:
- Reassign `string` to `string.strip(separator)` at the start (strip leading/trailing occurrences of characters contained in `separator`, per Python’s `str.strip` semantics).
- **Early returns**:
- If `max_length` is falsy (e.g., 0), return the stripped `string` unchanged.
- If `len(string)` is strictly less than `max_length`, return `string` unchanged.
- **Non-word-boundary truncation (`word_boundary` is False)**:
- Compute `substring = string[:max_length]` (first `max_length` characters).
- Return `substring.strip(separator)` (again using Python `str.strip` semantics).
- **Word-boundary truncation (`word_boundary` is True)**:
- If `separator` does not occur anywhere in the stripped `string` (i.e., `separator not in string`), return `string[:max_length]` with no additional stripping.
- Otherwise, build a truncated result by iterating tokens from `string.split(separator)` in order:
- Maintain `truncated` as an accumulating string, initially `''`.
- For each `word` produced by the split:
- If `word` is empty, skip it and continue (this can occur with repeated separators).
- Compute `next_len = len(truncated) + len(word)`.
- If `next_len < max_length`:
- Append `word` followed by `separator` to `truncated` (i.e., `truncated += word + separator`).
- Else if `next_len == max_length`:
- Append `word` to `truncated` (without adding a trailing `separator`), then stop iterating.
- Else (`next_len > max_length`):
- If `save_order` is True, stop iterating immediately.
- If `save_order` is False, do not modify `truncated` and continue iterating (later words may still be appended if they fit given the current `truncated` length).
- After the loop:
- If `truncated` is still empty (no word could be added under the above rules), fall back to `string[:max_length]` (using the already stripped `string` value).
- Otherwise, return `truncated.strip(separator)` (strip leading/trailing occurrences of characters contained in `separator`).
- **Invariants / guarantees**:
- When `max_length` is truthy, the returned string length is never greater than `max_length` (it may be shorter due to stripping or inability to add any full word under the word-boundary rules).
- When `word_boundary` is True and `save_order` is False, the algorithm may skip a too-long token and still include later shorter tokens; the returned tokens may not be a strict prefix of the original token sequence.
- The function does not mutate external state and depends only on its inputs.

**Returns**:
- (str): The truncated string according to the rules above; if `max_length` is falsy, returns the stripped input unchanged; otherwise returns a string of length at most `max_length` (possibly shorter after stripping).

---

## Function: slugify

```python
def slugify(text: str, entities: bool=True, decimal: bool=True, hexadecimal: bool=True, max_length: int=0, word_boundary: bool=False, separator: str=DEFAULT_SEPARATOR, save_order: bool=False, stopwords: Iterable[str]=(), regex_pattern: re.Pattern[str] | str | None=None, lowercase: bool=True, replacements: Iterable[Iterable[str]]=(), allow_unicode: bool=False) -> str
```

**slugify**: Convert input text into a URL/filename-safe “slug” by normalizing, optionally decoding HTML entities, applying deterministic ASCII-folding transliteration when Unicode is not allowed (via an exposed, monkeypatchable module-global `unidecode` hook), removing disallowed characters, removing stopwords, and optionally truncating.

**Signature**: def slugify(text: str, entities: bool = True, decimal: bool = True, hexadecimal: bool = True, max_length: int = 0, word_boundary: bool = False, separator: str = DEFAULT_SEPARATOR, save_order: bool = False, stopwords: Iterable[str] = (), regex_pattern: re.Pattern[str] | str | None = None, lowercase: bool = True, replacements: Iterable[Iterable[str]] = (), allow_unicode: bool = False) -> str

**Parameters**:
- text (str): Input text to slugify. If not a `str`, it is converted to text as described under **Behavior** (bytes-like are decoded deterministically; other objects use `str()`).
- entities (bool): If True, replace named HTML entities like `&amp;` with their Unicode character.
- decimal (bool): If True, replace decimal numeric character references like `&#169;` with their Unicode character; errors are ignored (see **Behavior**).
- hexadecimal (bool): If True, replace hexadecimal numeric character references like `&#xA9;` with their Unicode character; errors are ignored (see **Behavior**).
- max_length (int): If > 0, apply `smart_truncate` to the intermediate slug using `DEFAULT_SEPARATOR` as the separator.
- word_boundary (bool): Passed to `smart_truncate` when `max_length > 0`.
- separator (str): Final separator to use between slug tokens. If different from `DEFAULT_SEPARATOR`, the function replaces `DEFAULT_SEPARATOR` with this value at the end.
- save_order (bool): Passed to `smart_truncate` when `max_length > 0`.
- stopwords (Iterable[str]): Words to remove from the slug after cleanup; compared against tokens split on `DEFAULT_SEPARATOR`.
- regex_pattern (re.Pattern[str] | str | None): Custom regex (compiled pattern or pattern string) used to identify disallowed characters; if None, a built-in pattern is chosen based on `allow_unicode`.
- lowercase (bool): If True, lowercase the text during processing; also affects stopword matching (stopwords are lowercased for comparison).
- replacements (Iterable[Iterable[str]]): Sequence of `(old, new)` pairs (iterables of two strings) applied via `str.replace`; applied once at the start and again near the end.
- allow_unicode (bool): If True, keep Unicode characters (with Unicode-aware cleanup). If False, produce an ASCII-only slug using deterministic transliteration rules (see **Behavior**); output must not depend on whether optional third-party packages are installed.

**Behavior**:
- **Module-level integration point and monkeypatching contract (required for compatibility/patching)**:
- The function `slugify` MUST be defined in a module that also defines a module-global symbol named `unidecode`.
- Tests/callers are allowed to monkeypatch by doing module-level patching (e.g., `import <module>; <module>.unidecode = <callable>`). Therefore:
- `slugify` MUST look up and call `unidecode` from its own module global namespace at call time (late binding), not from a cached local reference and not from an unrelated library import that would bypass patching.
- The patching target is the module attribute `unidecode` (not an attribute on the `slugify` function object). The shipped module MUST make `unidecode` accessible as `<module>.unidecode`.
- **Required shape of `unidecode` for `slugify`**:
- `unidecode` MUST be directly callable: `unidecode(value) -> str | bytes-like | other`.
- `slugify` MUST call it exactly like `text = globals()['unidecode'](text)` (equivalent late-bound module-global lookup is acceptable), not as `unidecode.unidecode(text)` and not via any other indirection.
- If a caller assigns `<module>.unidecode = lambda s: ...`, `slugify` MUST immediately use that replacement on the next call.
- `unidecode` is used only when `allow_unicode` is False.

- **Apply user-specific replacements (pre-pass)**:
- If `replacements` is truthy, iterate `for old, new in replacements` and set `text = text.replace(old, new)` for each pair, in order.

- **Ensure `text` is a Unicode `str` (deterministic, never-throwing for bytes-like input)**:
- If `text` is an instance of `str`, keep it as-is.
- Else if `text` is bytes-like (`bytes`, `bytearray`, or `memoryview`):
- Convert to `bytes` if needed (e.g., `bytes(text)` for `bytearray`/`memoryview`).
- Decode using UTF-8 with a non-throwing error policy (e.g., `errors="replace"` or an equivalent strategy that guarantees a `str` result).
- **Invariants for bytes-like input**:
- This decode step MUST NOT raise a `UnicodeDecodeError`.
- For bytes that are valid UTF-8, the decoded `str` MUST be identical to what strict UTF-8 decoding would produce.
- **Pipeline equivalence requirement**:
- For any valid UTF-8 bytes input `b` and any `s` equal to `b.decode("utf-8")`, the full slugification pipeline MUST be equivalent: `slugify(b, ...)` MUST return exactly the same result as `slugify(s, ...)` for the same parameters.
- This equivalence covers every later step (apostrophes, normalization, optional transliteration, entity decoding, re-normalization, lowercasing, cleanup, separator collapsing/trimming, stopword removal, truncation, final separator substitution).
- No behavior after the initial conversion to `str` may branch on whether the original input was bytes-like vs `str`.
- Else (all other types), convert using `str(text)`.

- **Apply normalization and entity decoding in an order that preserves bytes/`str` equivalence**:
- After the initial conversion to `str`, all subsequent processing steps MUST operate on that `str` in the same order regardless of the original input type.
- In particular, accent/diacritic handling MUST be identical for `str` input and for bytes-like input that decodes to the same `str`. This means normalization and (when `allow_unicode` is False) transliteration/combining-mark removal MUST occur in the same sequence and with the same rules.

- **Pre-process ASCII apostrophes**:
- Replace one-or-more ASCII apostrophes (`'`) with `DEFAULT_SEPARATOR` via regex substitution. (This is an early pass that turns contractions/possessives into token boundaries.)

- **Normalize and optionally transliterate**:
- If `allow_unicode` is True:
- Normalize using Unicode normalization form `NFKC`.
- Do not transliterate to ASCII.
- Else (`allow_unicode` is False):
- Normalize using Unicode normalization form `NFKD`.
- Transliterate via the module-level `unidecode` hook:
- Call `text = unidecode(text)` where `unidecode` is obtained from the module global each call (so monkeypatching affects behavior).
- **The `unidecode` hook contract (including monkeypatch behavior)**:
- The return value of `unidecode(text)` fully replaces the current `text` for all subsequent steps (i.e., downstream processing continues from this returned value, after the conversions described below).
- It MAY return `str` or bytes-like (`bytes`, `bytearray`, `memoryview`).
- If it returns bytes-like, `slugify` MUST decode it to `str` immediately using the same deterministic, never-throwing UTF-8 decode rule used for bytes-like `text` input (non-throwing; valid UTF-8 preserved exactly; deterministic).
- If it returns any other non-`str` type, convert using `str(value)` (after the bytes-like check).
- **Ordering invariant for bytes returned from `unidecode`**:
- The decode of bytes returned by `unidecode` happens immediately after the hook call, and then the pipeline continues normally from the decoded string; there must be no special-case branch that reverts to the pre-hook string or applies an alternative transliteration path.

- **Deterministic transliteration requirement (normative, for the shipped/default `unidecode` implementation)**:
- The shipped/default `unidecode` MUST be deterministic and MUST yield stable output regardless of whether optional third-party packages are installed.
- The shipped/default `unidecode` MUST implement ASCII-folding (Latin-script transliteration) rather than deletion of non-ASCII letters.
- **Minimum quality bar**:
- For letters that are Latin letters with diacritics, the transliteration MUST produce their closest ASCII base letter(s) (e.g., diacritics removed), not an empty string.
- For Latin letters that do not decompose into ASCII base letters under `NFKD` (i.e., “non-decomposing letters”), the transliteration MUST still map them to an ASCII approximation rather than discarding them.
- For common Latin ligatures and compatibility letters, the transliteration MUST expand them to multi-letter ASCII sequences where appropriate (e.g., ligature expansion), not drop them.
- For characters outside Latin script (or otherwise not reasonably ASCII-foldable), the transliteration MAY map to an ASCII approximation if the implementation defines one; otherwise it MAY leave them as non-ASCII to be handled by later cleanup (they will become separators/removed). It MUST NOT introduce environment-dependent behavior for such characters.
- **Non-deletion invariant for foldable letters**:
- If a Unicode code point is a letter and has a reasonable Latin/ASCII folding (including “Latin letters with diacritics,” “Latin Extended letters,” and “Latin ligatures/compatibility letters”), the transliteration MUST yield at least one ASCII letter for it; it MUST NOT be silently dropped.
- **Canonical invariants for Latin folding (examples are illustrative, not exhaustive)**:
- For any precomposed Latin letter with a diacritic that has an ASCII base letter, the transliteration output MUST equal that base letter (case-preserving until the later lowercase step).
- For any Latin Extended letter commonly treated as a modified form of an ASCII letter (including those with strokes, hooks, ogoneks, carons, dots, cedillas, rings, tildes, and similar marks), transliteration MUST map it to its conventional ASCII base letter (or base-letter pair where conventional).
- For any common ligature (Latin), transliteration MUST map it to its conventional expansion (multiple ASCII letters).
- **Environment-independence invariants**:
- The shipped/default `unidecode` MUST NOT change behavior based on the presence/absence/version of external packages.
- If the implementation chooses to embed a mapping table, it MUST be internal and deterministic.
- If the implementation chooses to emulate a known transliteration scheme, it MUST do so deterministically and must not fall back to “drop non-ASCII” behavior.
- **End-to-end ASCII folding invariant (required for `allow_unicode=False`)**:
- For inputs containing Latin letters with diacritics (including those provided as UTF-8 bytes that decode to the same Unicode string), the final slug MUST preserve the underlying letters by ASCII-folding them (diacritics removed/expanded) rather than removing those letters.

- **Decode HTML references (each step conditional, operating on the current `text`)**:
- If `entities` is True:
- Replace named entities matching `&<name>;` where `<name>` is any key in `html.entities.name2codepoint`, with `chr(name2codepoint[name])`.
- If `decimal` is True:
- Attempt to replace decimal references matching `&#(\d+);` with `chr(int(value))`.
- Wrap the substitution in a broad `try/except Exception`; on any exception (including invalid code points), leave `text` unchanged for this step.
- If `hexadecimal` is True:
- Attempt to replace hex references matching `&#x([\da-fA-F]+);` with `chr(int(value, 16))`.
- Wrap the substitution in a broad `try/except Exception`; on any exception (including invalid code points), leave `text` unchanged for this step.

- **Re-normalize after entity decoding**:
- If `allow_unicode` is True, normalize with `NFKC`; else normalize with `NFKD`.
- If `allow_unicode` is False:
- This re-normalization MUST NOT introduce environment-dependent transliteration.
- If additional ASCII conversion is needed after re-normalization to satisfy the ASCII-only slug requirement, it MUST still be deterministic and MUST still satisfy the non-deletion invariant for foldable letters (e.g., by routing through the same module-level `unidecode` hook again or by applying an equivalent deterministic folding step that does not depend on external packages).

- **Optional lowercasing**:
- If `lowercase` is True, set `text = text.lower()`.

- **Post-process ASCII apostrophes**:
- Remove one-or-more ASCII apostrophes (`'`) entirely (replace with empty string) via regex substitution. (This is a later cleanup pass after lowercasing.)

- **Cleanup numbers**:
- Remove commas that are between digits (pattern equivalent to “comma with a digit before and after”) by replacing them with empty string.

- **Replace disallowed characters with `DEFAULT_SEPARATOR`**:
- Choose `pattern`:
- If `regex_pattern` is provided (compiled pattern or pattern string), use it directly as the first argument to `re.sub`.
- Else if `allow_unicode` is True:
- Use a built-in pattern that matches one-or-more of any non-word character or underscore (so letters/digits from Unicode word categories are generally kept; underscores are treated as separators).
- Else (`allow_unicode` is False):
- Use a built-in pattern that matches one-or-more characters not in `[-a-zA-Z0-9]` (ASCII-only slug requirement).
- Apply `re.sub(pattern, DEFAULT_SEPARATOR, text)`.
- **Separator/whitespace invariants**:
- Any leading/trailing whitespace or punctuation that matches the disallowed-character pattern MUST become `DEFAULT_SEPARATOR` first, and will then be subject to the same collapsing and trimming rules described below. This guarantees consistent treatment of leading/trailing “separator-like” content and is part of the bytes/`str` equivalence invariant.

- **Collapse and trim separators (must be based on `DEFAULT_SEPARATOR`, not hard-coded to `"-"`)**:
- Replace runs of two-or-more `DEFAULT_SEPARATOR` characters with a single `DEFAULT_SEPARATOR`.
- This collapsing regex must be constructed using `DEFAULT_SEPARATOR` as a variable (e.g., via `re.escape(DEFAULT_SEPARATOR)`), so the behavior is correct even if `DEFAULT_SEPARATOR` is changed from its typical value.
- Strip leading and trailing `DEFAULT_SEPARATOR` characters.
- **Invariant**:
- After this step, the intermediate slug MUST NOT start or end with `DEFAULT_SEPARATOR`, regardless of whether the original input began/ended with whitespace, punctuation, or other disallowed characters.

- **Remove stopwords (if any)**:
- If `stopwords` is truthy:
- Split `text` on `DEFAULT_SEPARATOR` into tokens.
- If `lowercase` is True:
- Lowercase each stopword into a list (or set) `stopwords_lower`.
- Keep only tokens `w` such that `w not in stopwords_lower`.
- Else:
- Keep only tokens `w` such that `w not in stopwords` (using the iterable as provided, with exact matching).
- Re-join remaining tokens with `DEFAULT_SEPARATOR`.

- **Apply user-specific replacements again (post-pass)**:
- If `replacements` is truthy, again iterate `for old, new in replacements` and apply `text = text.replace(old, new)` in order.
- This second pass occurs after cleanup and stopword removal, so replacements can affect the final slug tokens.

- **Optional truncation**:
- If `max_length > 0`, set `text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)`.
- **Truncation invariants**:
- Truncation operates on the slug that uses `DEFAULT_SEPARATOR`, regardless of the requested final `separator`.
- The output of truncation MUST preserve the “no leading/trailing `DEFAULT_SEPARATOR`” invariant.

- **Final separator substitution**:
- If `separator != DEFAULT_SEPARATOR`, replace all occurrences of `DEFAULT_SEPARATOR` in `text` with `separator`.
- Note: stopword tokenization and truncation always operate on `DEFAULT_SEPARATOR`; the custom `separator` is applied only at the end.

- **Deterministic equivalence examples (non-exhaustive, illustrative of required invariants)**:
- For any Unicode string `s` and any UTF-8 bytes `b` such that `b.decode('utf-8') == s`, calling `slugify` on `s` vs `b` with the same parameters MUST yield identical output.
- When `allow_unicode` is False, inputs that differ only by Unicode composition (e.g., precomposed vs decomposed forms of the same graphemes) MUST slugify identically, because NFKD + deterministic ASCII-folding transliteration must converge them before ASCII cleanup.
- When `allow_unicode` is False, for any input consisting of ASCII plus Latin letters with diacritics (including those represented as UTF-8 bytes), the output MUST be the same as if those letters had been replaced by their ASCII-folded equivalents prior to slugification (i.e., letters are preserved by folding, not removed).
- If a monkeypatched `unidecode` returns UTF-8 bytes representing some ASCII/Unicode text, the pipeline MUST continue as if `unidecode` had returned the corresponding `str` (subject to the same lowercasing, cleanup, stopword removal, truncation, and separator substitution rules).

**Returns**:
- (str): The slugified string after all enabled transformations. Invariants:
- The function MUST be total (should not raise) for bytes-like input due to decoding; bytes-like decoding MUST be deterministic and never-throwing.
- For any valid UTF-8 bytes input `b` and the equivalent `str` `s = b.decode("utf-8")`, `slugify(b, ...)` MUST equal `slugify(s, ...)` for the same parameters, including identical trimming/collapsing and any effects of entity decoding, normalization, and transliteration.
- If `allow_unicode` is False, the returned slug contains only ASCII letters, digits, and the chosen separator, and its content is deterministic across environments and dependency sets.
- If `allow_unicode` is False, Latin letters with diacritics and other ASCII-foldable Latin letters MUST be preserved via ASCII folding (diacritics removed/ligatures expanded) rather than being dropped.
- The returned slug MUST NOT begin or end with the (final) separator (subject to the behavior of `smart_truncate` and the collapse/trim invariants described above).
