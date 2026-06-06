# NOTE: This module intentionally defines only the public functions
# `smart_truncate` and `slugify`, plus the required module-global `unidecode`
# hook and `DEFAULT_SEPARATOR` constant used by `slugify`.

import re
import unicodedata
import html.entities

DEFAULT_SEPARATOR = "-"


def unidecode(value):
    """Deterministic ASCII-folding transliteration hook.

    This default implementation is intentionally simple and deterministic.
    Callers may monkeypatch the module-global `unidecode` symbol.
    """

    if isinstance(value, str):
        text = value
    elif isinstance(value, (bytes, bytearray, memoryview)):
        text = bytes(value).decode("utf-8", errors="replace")
    else:
        text = str(value)

    text = unicodedata.normalize("NFKD", text)

    out = []
    for ch in text:
        o = ord(ch)

        if o < 128:
            out.append(ch)
            continue

        if unicodedata.combining(ch):
            continue

        # Minimal deterministic folding for common non-decomposing Latin letters
        # and ligatures.
        if ch == "ß":
            out.append("ss")
            continue
        if ch == "ẞ":
            out.append("SS")
            continue
        if ch in ("Æ", "Ǽ", "Ǣ"):
            out.append("AE")
            continue
        if ch in ("æ", "ǽ", "ǣ"):
            out.append("ae")
            continue
        if ch == "Œ":
            out.append("OE")
            continue
        if ch == "œ":
            out.append("oe")
            continue
        if ch == "Ĳ":
            out.append("IJ")
            continue
        if ch == "ĳ":
            out.append("ij")
            continue
        if ch == "Ð":
            out.append("D")
            continue
        if ch == "ð":
            out.append("d")
            continue
        if ch == "Þ":
            out.append("Th")
            continue
        if ch == "þ":
            out.append("th")
            continue
        if ch == "Ł":
            out.append("L")
            continue
        if ch == "ł":
            out.append("l")
            continue
        if ch == "Ø":
            out.append("O")
            continue
        if ch == "ø":
            out.append("o")
            continue
        if ch == "Đ":
            out.append("D")
            continue
        if ch == "đ":
            out.append("d")
            continue
        if ch == "Ħ":
            out.append("H")
            continue
        if ch == "ħ":
            out.append("h")
            continue
        if ch == "Ŋ":
            out.append("N")
            continue
        if ch == "ŋ":
            out.append("n")
            continue
        if ch == "Ŧ":
            out.append("T")
            continue
        if ch == "ŧ":
            out.append("t")
            continue
        if ch == "ŉ":
            out.append("n")
            continue

        decomp = unicodedata.normalize("NFKD", ch)
        folded = []
        for dch in decomp:
            if ord(dch) < 128 and not unicodedata.combining(dch):
                folded.append(dch)
        if folded:
            out.append("".join(folded))

    return "".join(out)


def smart_truncate(string: str, max_length: int = 0, word_boundary: bool = False, separator: str = " ", save_order: bool = False) -> str:
    string = string.strip(separator)

    if not max_length:
        return string

    if len(string) < max_length:
        return string

    if not word_boundary:
        substring = string[:max_length]
        return substring.strip(separator)

    if separator not in string:
        return string[:max_length]

    truncated = ""
    for word in string.split(separator):
        if not word:
            continue

        next_len = len(truncated) + len(word)
        if next_len < max_length:
            truncated += word + separator
        elif next_len == max_length:
            truncated += word
            break
        else:
            if save_order:
                break
            continue

    if not truncated:
        return string[:max_length]

    return truncated.strip(separator)


def slugify(
    text: str,
    entities: bool = True,
    decimal: bool = True,
    hexadecimal: bool = True,
    max_length: int = 0,
    word_boundary: bool = False,
    separator: str = DEFAULT_SEPARATOR,
    save_order: bool = False,
    stopwords=(),
    regex_pattern=None,
    lowercase: bool = True,
    replacements=(),
    allow_unicode: bool = False,
) -> str:
    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if isinstance(text, str):
        pass
    elif isinstance(text, (bytes, bytearray, memoryview)):
        try:
            text = bytes(text).decode("utf-8", errors="replace")
        except Exception:
            text = str(text)
    else:
        text = str(text)

    text = re.sub(r"'+", DEFAULT_SEPARATOR, text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        value = globals()["unidecode"](text)
        if isinstance(value, str):
            text = value
        elif isinstance(value, (bytes, bytearray, memoryview)):
            try:
                text = bytes(value).decode("utf-8", errors="replace")
            except Exception:
                text = str(value)
        else:
            text = str(value)

    if entities:
        def _ent(m):
            name = m.group(1)
            cp = html.entities.name2codepoint.get(name)
            if cp is None:
                return m.group(0)
            try:
                return chr(cp)
            except Exception:
                return m.group(0)

        text = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", _ent, text)

    if decimal:
        try:
            text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
        except Exception:
            pass

    if hexadecimal:
        try:
            text = re.sub(r"&#x([\da-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
        except Exception:
            pass

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        # Ensure ASCII-only deterministically after re-normalization
        value = globals()["unidecode"](text)
        if isinstance(value, str):
            text = value
        elif isinstance(value, (bytes, bytearray, memoryview)):
            try:
                text = bytes(value).decode("utf-8", errors="replace")
            except Exception:
                text = str(value)
        else:
            text = str(value)

    if lowercase:
        text = text.lower()

    text = re.sub(r"'+", "", text)
    text = re.sub(r"(?<=\d),(?=\d)", "", text)

    if regex_pattern is not None:
        pattern = regex_pattern
    else:
        if allow_unicode:
            pattern = r"[\W_]+"
        else:
            pattern = r"[^-a-zA-Z0-9]+"

    text = re.sub(pattern, DEFAULT_SEPARATOR, text)

    esc_sep = re.escape(DEFAULT_SEPARATOR)
    text = re.sub(esc_sep + r"{2,}", DEFAULT_SEPARATOR, text)
    text = text.strip(DEFAULT_SEPARATOR)

    if stopwords:
        tokens = text.split(DEFAULT_SEPARATOR) if text else []
        if lowercase:
            stopwords_lower = [str(w).lower() for w in stopwords]
            tokens = [w for w in tokens if w and w not in stopwords_lower]
        else:
            tokens = [w for w in tokens if w and w not in stopwords]
        text = DEFAULT_SEPARATOR.join(tokens)

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if max_length > 0:
        text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)

    if separator != DEFAULT_SEPARATOR:
        text = text.replace(DEFAULT_SEPARATOR, separator)

    return text
