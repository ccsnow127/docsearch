# __init__ Baseline Documentation

## Module: __init__

**Purpose**: Provides a Python inflection utility set (ported from Rails’ inflector) for converting words between singular/plural forms and transforming identifiers between common naming styles (snake_case, CamelCase, human-readable titles, URL slugs), using regex-based rules plus Unicode transliteration.

**Key data and relationships**: The module maintains global rule tables **PLURALS** and **SINGULARS** (ordered regex/replacement pairs) and an **UNCOUNTABLES** set; these are consumed by **pluralize** and **singularize**, and are extended at import time via **_irregular** calls that prepend irregular-word rules so they take precedence.

**Functions**:
- **_irregular(singular, plural)**: Inserts case-aware regex rules into **PLURALS**/**SINGULARS** for an irregular pair, ensuring correct handling of capitalization variants.
- **camelize(string, uppercase_first_letter=True)**: Converts underscore-delimited strings to UpperCamelCase or lowerCamelCase.
- **underscore(word)**: Converts CamelCase/mixed-case (and hyphens) to lowercase snake_case; used by higher-level helpers.
- **pluralize(word)** / **singularize(word)**: Convert between grammatical number using **PLURALS**/**SINGULARS**, with **UNCOUNTABLES** bypass logic.
- **tableize(word)**: Produces a Rails-style table name by applying **underscore** then **pluralize**.
- **humanize(word)**: Makes identifiers readable by removing a trailing “_id”, replacing underscores with spaces, lowercasing, and capitalizing the first character.
- **titleize(word)**: Produces title-cased, human-friendly text by composing **underscore** and **humanize** and then capitalizing word starts.
- **dasherize(word)**: Replaces underscores with hyphens.
- **transliterate(string)**: Normalizes Unicode (NFKD) and strips non-ASCII characters to create an ASCII approximation.
- **parameterize(string, separator='-')**: Builds URL-friendly slugs by composing **transliterate** with regex cleanup and separator collapsing/trimming.
- **ordinal(number)** / **ordinalize(number)**: Compute English ordinal suffixes and append them to numbers, respectively.

---

## Function: _irregular

```python
def _irregular(singular: str, plural: str) -> None
```

**_irregular**: Register pluralization and singularization regex rules for an irregular singular/plural word pair by prepending rules into the global rule lists, using case-insensitive matching while preserving the original word’s first-letter case via a capturing group.

**Signature**: def _irregular(singular: str, plural: str) -> None

**Parameters**:
- singular (str): The irregular word in singular form; must be indexable and have at least 1 character because the first character and the remainder are accessed.
- plural (str): The irregular word in plural form; must be indexable and have at least 1 character because the first character and the remainder are accessed.

**Behavior**:
- Mutates the module-level `PLURALS` and `SINGULARS` lists by inserting new `(pattern, replacement)` rules at index `0` (front of list) so they take precedence over existing rules.
- Assumes both inputs have length ≥ 1; accessing `singular[0]`, `singular[1:]`, `plural[0]`, `plural[1:]` will raise an indexing error if either is empty.
- Constructs and prepends rules using a single invariant strategy for all irregular pairs (including when the first letters differ):
  - All patterns are case-insensitive using the inline flag `(?i)`.
  - The first character of the matched word is captured as group 1 using parentheses around the first character literal, so the replacement can reuse `\1` to preserve the original first-letter case from the input word.
  - The remainder of the word (everything after the first character) is matched literally as `singular[1:]` or `plural[1:]` and anchored to end-of-string with `$`.
- Prepends exactly three rules in this order (each inserted at index 0, so the last inserted ends up first unless inserted in the specified sequence):
  - Into `PLURALS`: a rule matching the singular form at end-of-string:
    - pattern: `r"(?i)({}){}$".format(singular[0], singular[1:])`
    - replacement: `r"\1" + plural[1:]`
  - Into `PLURALS`: a rule matching the plural form at end-of-string (to normalize already-plural irregulars as plural):
    - pattern: `r"(?i)({}){}$".format(plural[0], plural[1:])`
    - replacement: `r"\1" + plural[1:]`
  - Into `SINGULARS`: a rule matching the plural form at end-of-string:
    - pattern: `r"(?i)({}){}$".format(plural[0], plural[1:])`
    - replacement: `r"\1" + singular[1:]`
- No alternate branch is used for “different first letter” pairs; the same `(?i)({first}){rest}$` + `\1` strategy is applied regardless of whether `singular[0].upper() == plural[0].upper()`.

**Returns**:
- None (operates via side effects on `PLURALS` and `SINGULARS`).

---

## Function: caseinsensitive

```python
def caseinsensitive(string: str) -> str
```

**caseinsensitive**: Convert a string into a regex fragment that matches each character in either lowercase or uppercase.
**Signature**: def caseinsensitive(string: str) -> str
**Parameters**:
- string (str): Input text whose characters will be expanded into per-character case-insensitive bracket expressions.
**Behavior**:
- Iterate through each character `char` in `string` in order.
- For each `char`, produce the substring `'[' + char + char.upper() + ']'`.
- Concatenate all produced substrings into one output string and return it.
- No regex escaping is performed; characters are inserted as-is.
**Returns**:
- (str): A concatenated regex fragment where each original character is replaced by a bracket expression containing the character and its uppercase form.

---

## Function: camelize

```python
def camelize(string: str, uppercase_first_letter: bool=True) -> str
```

**camelize**: Convert an underscore-delimited string into CamelCase, optionally using lowerCamelCase.
**Signature**: def camelize(string: str, uppercase_first_letter: bool=True) -> str
**Parameters**:
- string (str): Source string, typically containing underscores to denote word boundaries.
- uppercase_first_letter (bool): If True, produce UpperCamelCase; if False, produce lowerCamelCase.
**Behavior**:
- If `uppercase_first_letter` is True:
- Use a regex substitution over `string` with pattern `r"(?:^|_)(.)"`.
- For each match, replace it with the uppercase version of the single captured character (group 1), effectively removing underscores and uppercasing the character following the start or an underscore.
- Return the substituted string.
- Else (`uppercase_first_letter` is False):
- Compute `camelize(string)` using the default behavior (i.e., as if `uppercase_first_letter` were True).
- Lowercase the first character of the original `string` via `string[0].lower()` and concatenate it with the substring of the computed CamelCase result starting at index 1.
- Return that concatenation.
**Returns**:
- (str): The CamelCase-transformed string.
**Notes**:
- When `uppercase_first_letter` is False, the implementation indexes `string[0]`; an empty `string` will raise an indexing error.
- The lowerCamelCase branch lowercases the first character of the original input, not the first character of the CamelCase result, and then appends the CamelCase result from position 1 onward.

---

## Function: dasherize

```python
def dasherize(word: str) -> str
```

**dasherize**: Replace underscores with dashes in a string.
**Signature**: def dasherize(word: str) -> str
**Parameters**:
- word (str): Input string possibly containing underscores.
**Behavior**:
- Return a new string where every `'_'` character in `word` is replaced with `'-'`.
- No other transformations are applied.
**Returns**:
- (str): The transformed string with underscores replaced by dashes.

---

## Function: humanize

```python
def humanize(word: str) -> str
```

**humanize**: Produce a human-readable phrase by removing a trailing `_id`, converting underscores to spaces, lowercasing words, and capitalizing the first character.
**Signature**: def humanize(word: str) -> str
**Parameters**:
- word (str): Input identifier-like string, typically underscore-separated and possibly ending with `_id`.
**Behavior**:
- Remove a trailing `_id` if present by applying a regex substitution with pattern `r"_id$"` replacing with the empty string.
- Replace all underscores with spaces.
- Lowercase content by applying a regex substitution with pattern `r"(?i)([a-z\d]*)"` and replacement function that returns `m.group(1).lower()`.
- This operates case-insensitively and targets runs of letters/digits (including possibly empty matches), ensuring letters become lowercase while leaving non-alphanumeric separators (like spaces) intact.
- Capitalize the first word character by applying a regex substitution with pattern `r"^\w"` and replacement function that uppercases the matched character.
- Return the resulting string.
**Returns**:
- (str): A human-friendly version of the input.

---

## Function: ordinal

```python
def ordinal(number: int) -> str
```

**ordinal**: Compute the English ordinal suffix for an integer (e.g., `st`, `nd`, `rd`, `th`).
**Signature**: def ordinal(number: int) -> str
**Parameters**:
- number (int): The number whose ordinal suffix is needed; will be coerced with `int()` and handled by absolute value.
**Behavior**:
- Convert `number` to an integer with `int(number)` and take its absolute value.
- If `number % 100` is 11, 12, or 13, return `'th'`.
- Otherwise, compute `number % 10` and return:
- `'st'` if the remainder is 1
- `'nd'` if the remainder is 2
- `'rd'` if the remainder is 3
- `'th'` for any other remainder
**Returns**:
- (str): The ordinal suffix corresponding to the input number after integer coercion and absolute value.

---

## Function: ordinalize

```python
def ordinalize(number: int) -> str
```

**ordinalize**: Convert an integer into its ordinal string form by appending the appropriate suffix.
**Signature**: def ordinalize(number: int) -> str
**Parameters**:
- number (int): The number to convert; passed to `ordinal(number)` to determine the suffix.
**Behavior**:
- Compute the suffix by calling `ordinal(number)`.
- Format and return a string consisting of the original `number` (as formatted by `str(number)` via `format`) immediately followed by the suffix.
**Returns**:
- (str): The ordinalized representation, e.g., `1st`, `-11th`.

---

## Function: parameterize

```python
def parameterize(string: str, separator: str='-') -> str
```

**parameterize**: Convert a string into a URL-friendly “slug” by transliterating to ASCII, replacing unwanted characters with a separator, collapsing repeats, trimming, and lowercasing.
**Signature**: def parameterize(string: str, separator: str='-') -> str
**Parameters**:
- string (str): Input text to slugify; will be transliterated to ASCII before further processing.
- separator (str): String used to replace runs of unwanted characters; if non-empty, it is also collapsed and trimmed from ends.
**Behavior**:
- Convert `string` to an ASCII approximation by calling `transliterate(string)`.
- Replace runs of characters not in the set `[a-z0-9\-_]` (case-insensitive) with `separator` using regex substitution pattern `r"(?i)[^a-z0-9\-_]+"`.
- If `separator` is a non-empty string:
- Escape it for regex use via `re.escape(separator)` and store as `re_sep`.
- Collapse consecutive separators into a single separator by substituting pattern `r'%s{2,}' % re_sep` with `separator`.
- Remove a leading or trailing separator by substituting pattern `r"(?i)^{sep}|{sep}$".format(sep=re_sep)` with the empty string.
- Return the final string lowercased with `.lower()`.
**Returns**:
- (str): A lowercased, separator-delimited slug.
**Notes**:
- If `separator` is the empty string, unwanted characters are replaced with `''` and no collapsing/trimming step is performed.

---

## Function: pluralize

```python
def pluralize(word: str) -> str
```

**pluralize**: Return the plural form of an English word by applying a pre-populated set of inflection rules (regular, irregular, and uncountable) expressed as regex substitutions.

**Signature**: def pluralize(word: str) -> str

**Parameters**:
- word (str): Input word to pluralize. Expected to be a single English word; may include mixed case.

**Behavior**:
- Dependency/initialization requirement:
  - This function is rule-driven and depends on two module-level globals being populated before `pluralize` is used:
    - `UNCOUNTABLES`: a set of lowercase strings representing nouns that do not inflect for number (e.g., mass nouns and invariant plurals). These entries must be stored in lowercase, and membership checks are performed using `word.lower()`.
    - `PLURALS`: an ordered list of `(rule, replacement)` pairs where:
      - `rule` is a regex pattern string.
      - `replacement` is a replacement string compatible with `re.sub`, including backreferences when needed.
  - Implementations must ensure that a default English ruleset is loaded into these globals (either at import time or via helper setup functions executed before calling `pluralize`). The default ruleset must include:
    - A baseline collection of regular pluralization patterns (e.g., adding suffixes, handling common endings).
    - A collection of irregular singular→plural mappings that are installed as higher-precedence rules than regular patterns (commonly by prepending to `PLURALS`), so irregulars match before generic suffix rules.
    - A collection of uncountable words added to `UNCOUNTABLES`.
  - If these globals are left empty or not initialized, `pluralize` will typically return the input unchanged for most words; callers/tests that expect English inflection assume the globals are populated.
- Algorithm:
  - If `word` is falsy (e.g., empty string), return `word` unchanged.
  - Compute `lower = word.lower()`.
  - If `lower` is present in `UNCOUNTABLES`, return `word` unchanged.
  - Otherwise, iterate through `PLURALS` in list order (first rule has highest precedence):
    - For each `(rule, replacement)`:
      - If `re.search(rule, word)` is truthy, return `re.sub(rule, replacement, word)` immediately.
  - If no rule matches, return `word` unchanged.
- Rule precedence and invariants:
  - Rule order matters; the first matching rule wins.
  - Irregular rules must be ordered ahead of regular rules to ensure correct results for words that would otherwise match a generic pattern.
  - Rules are applied to the original `word` string (not the lowercased form), while uncountable detection is case-insensitive via `word.lower()`.
- Side effects:
  - `pluralize` does not mutate `PLURALS` or `UNCOUNTABLES`; it only reads them. Any setup/mutation is expected to occur elsewhere (e.g., module initialization or helper functions).

**Returns**:
- (str): The pluralized form of `word` if it is countable and a rule matches; otherwise the original `word` unchanged.

---

## Function: singularize

```python
def singularize(word: str) -> str
```

**singularize**: Return the singular form of an English word by applying a caller-/module-provided ordered list of regex substitution rules, while leaving configured uncountable words unchanged.

**Signature**: def singularize(word: str) -> str

**Parameters**:
- word (str): Input word to singularize. Treated as an arbitrary string; the function does not validate that it is alphabetic.

**Behavior**:
- **Module surface area constraint**:
- This module/entity is specified to provide **only** the `singularize` function behavior described here. It must not add unrelated public APIs (for example, pluralization, casing, humanization helpers) as part of implementing `singularize`.
- **Global data dependency and side-effect constraints**:
- `singularize` depends on two pre-existing globals in the same module namespace:
- `UNCOUNTABLES`: a collection of uncountable terms.
- `SINGULARS`: an ordered sequence of `(rule, replacement)` pairs used for singularization.
- `singularize` must be a pure function with respect to module state:
- It must not populate, modify, reorder, or otherwise mutate `UNCOUNTABLES` or `SINGULARS`.
- It must not install a “default ruleset”, append/prepend rules, or create additional rules at import time or at call time.
- It must not have any other side effects (no I/O, no logging, no environment inspection).
- **Uncountables matching contract**:
- Uncountable entries are treated as literal strings (not regex fragments).
- For matching, each uncountable entry must be safely escaped (e.g., via `re.escape`) before use in any regex.
- Matching is case-insensitive.
- An uncountable term matches **only when the entire input string is exactly that term** (ignoring case). In other words, uncountables are an exact-term exemption, not a suffix/prefix exemption.
- Therefore, the check must behave equivalently to an anchored full-string match such as `(?i)\A<escaped_inflection>\Z` (or an equivalent mechanism such as `word.casefold() == inflection.casefold()`), and must not use “end-of-string with word-boundary” logic that could also match a term as a suffix inside a longer token.
- Consequence/invariant: having an uncountable base term must not automatically exempt longer strings that merely contain that term (including strings that add letters before or after it) from singularization; only exact equality qualifies.
- If any uncountable term matches under the exact-term rule above, return `word` unchanged immediately.
- **Determinism requirements for uncountables**:
- The function’s result must not depend on iteration order of uncountables; since the action on any match is “return the original word unchanged”, uncountables are conceptually a membership test. Any iterable container may be used, but the observable behavior must be the same regardless of container ordering.
- **Rule application contract**:
- If `word` is not treated as uncountable, iterate through `SINGULARS` in the given order (order is significant and must be respected exactly as provided).
- Each element of `SINGULARS` is a pair `(rule, replacement)` where:
- `rule` is a regex pattern string compatible with `re.search`/`re.sub`.
- `replacement` is a replacement string compatible with `re.sub`.
- For the first `(rule, replacement)` pair where `re.search(rule, word)` is truthy, return `re.sub(rule, replacement, word)` immediately.
- Only the first matching rule is applied; do not apply multiple rules.
- If no rules match, return `word` unchanged.
- **Error handling / edge cases**:
- The function does not catch regex compilation/execution errors; invalid patterns in `SINGULARS` (or misuse of types) may raise the underlying `re` exceptions.
- If `word` is an empty string, it will either match no rules and be returned unchanged, or be transformed only if a provided rule matches the empty string.

**Returns**:
- (str): The singularized form of `word` if `word` is not matched as uncountable and at least one rule in `SINGULARS` matches; otherwise the original `word` unchanged.

---

## Function: tableize

```python
def tableize(word: str) -> str
```

**tableize**: Convert a model/class-like name into a Rails-style table name by underscoring it and pluralizing the result.
**Signature**: def tableize(word: str) -> str
**Parameters**:
- word (str): Input identifier (may be CamelCase, lowerCamelCase, already underscored, and/or contain hyphens).
**Behavior**:
- Convert the input to an underscored lowercase form by calling `underscore(word)`.
- Pluralize the underscored result by calling `pluralize(...)`.
- Do not perform any additional validation or special-casing beyond what `underscore` and `pluralize` do.
**Returns**:
- The pluralized, underscored table name as a `str`.
**Notes**:
- Any edge cases (e.g., empty string, uncountables) are handled by `pluralize`; casing/hyphen handling is handled by `underscore`.

---

## Function: titleize

```python
def titleize(word: str) -> str
```

**titleize**: Produce a human-friendly title by underscoring/camel-splitting, humanizing, title-casing, and then capitalizing word-initial characters (including after apostrophes).
**Signature**: def titleize(word: str) -> str
**Parameters**:
- word (str): Input text/identifier that may contain spaces, underscores, hyphens, punctuation, and/or CamelCase.
**Behavior**:
- First transform the input with `underscore(word)` to split CamelCase and normalize hyphens to underscores.
- Pass that result to `humanize(...)` to:
- Remove a trailing `_id` if present.
- Replace underscores with spaces.
- Lowercase the content (via a regex-based lowercasing step) and then capitalize the first character of the whole string.
- Call `.title()` on the humanized string to title-case it (capitalize the first character of each word as defined by Python’s `str.title`).
- Finally, run a regex substitution over the title-cased string:
- Pattern: `\b('?\w)` (a word boundary followed by an optional apostrophe and then a single “word” character).
- For each match, replace it with `match.group(1).capitalize()`.
- This last step ensures the matched initial character (or apostrophe+character) is capitalized using `str.capitalize` on that 1–2 character substring.
- Return the resulting string.
**Returns**:
- A titleized version of the input as a `str`.
**Notes**:
- This function depends on `underscore` and `humanize` for most normalization; punctuation such as colons may remain, while underscores/hyphens and CamelCase boundaries are converted into spaces before title casing.

---

## Function: transliterate

```python
def transliterate(string: str) -> str
```

**transliterate**: Convert Unicode text to an ASCII-only approximation by decomposing characters and dropping any non-ASCII bytes.
**Signature**: def transliterate(string: str) -> str
**Parameters**:
- string (str): Unicode text to transliterate.
**Behavior**:
- Normalize the input using Unicode normalization form `NFKD` via `unicodedata.normalize('NFKD', string)`.
- Encode the normalized string to ASCII with `errors='ignore'`, which drops any characters that cannot be represented in ASCII.
- Decode the resulting ASCII bytes back into a Python `str` using ASCII decoding.
- Return the decoded ASCII string.
**Returns**:
- An ASCII-only `str` where representable characters are preserved (often via decomposition) and unrepresentable characters are omitted.
**Notes**:
- Characters without an ASCII decomposition/representation are removed rather than replaced with placeholders.

---

## Function: underscore

```python
def underscore(word: str) -> str
```

**underscore**: Convert CamelCase/mixed-case identifiers into lowercase snake_case, also converting hyphens to underscores.
**Signature**: def underscore(word: str) -> str
**Parameters**:
- word (str): Input identifier/text that may contain uppercase sequences, lowercase letters, digits, and hyphens.
**Behavior**:
- Insert an underscore between an uppercase sequence and a following Capitalized word part:
- Apply `re.sub(r"([A-Z]+)([A-Z][a-z])", r'\1_\2', word)`.
- This targets boundaries like `HTTPServer` -> `HTTP_Server` (splitting before the last capital that starts a Capital+lowercase run).
- Insert an underscore between a lowercase letter or digit and a following uppercase letter:
- Apply `re.sub(r"([a-z\d])([A-Z])", r'\1_\2', word)`.
- This targets boundaries like `deviceType` -> `device_Type`.
- Replace all hyphens `-` with underscores `_` using `word.replace("-", "_")`.
- Convert the entire string to lowercase with `.lower()`.
- Return the resulting string.
**Returns**:
- A lowercase, underscored `str`.
**Notes**:
- The transformation is purely pattern-based; it does not attempt to preserve acronyms beyond the regex splitting behavior described above.
