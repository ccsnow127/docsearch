import re
import unicodedata
import html.entities

DEFAULT_SEPARATOR = "-"

__all__ = [
    "DEFAULT_SEPARATOR",
    "ENTITY_PATTERN",
    "DECIMAL_PATTERN",
    "HEX_PATTERN",
    "unidecode",
    "smart_truncate",
    "slugify",
]

ENTITY_PATTERN = re.compile(r"&([A-Za-z][A-Za-z0-9]+);")
DECIMAL_PATTERN = re.compile(r"&#([0-9]+);")
HEX_PATTERN = re.compile(r"&#x([0-9A-Fa-f]+);")

_ASCII_APOSTROPHE_TO_SEP_RE = re.compile(r"'+")
_ASCII_APOSTROPHE_REMOVE_RE = re.compile(r"'+")
_COMMA_BETWEEN_DIGITS_RE = re.compile(r"(?<=\d),(?=\d)")


def unidecode(value):
    if not isinstance(value, str):
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                value = bytes(value).decode("utf-8", errors="replace")
            except Exception:
                value = str(value)
        else:
            value = str(value)

    value = unicodedata.normalize("NFKD", value)

    out = []
    for ch in value:
        if unicodedata.combining(ch):
            continue
        o = ord(ch)
        if o < 128:
            out.append(ch)
            continue

        if ch in ("ß",):
            out.append("ss")
            continue
        if ch in ("Æ",):
            out.append("AE")
            continue
        if ch in ("æ",):
            out.append("ae")
            continue
        if ch in ("Œ",):
            out.append("OE")
            continue
        if ch in ("œ",):
            out.append("oe")
            continue
        if ch in ("Ø",):
            out.append("O")
            continue
        if ch in ("ø",):
            out.append("o")
            continue
        if ch in ("Ð",):
            out.append("D")
            continue
        if ch in ("ð",):
            out.append("d")
            continue
        if ch in ("Þ",):
            out.append("Th")
            continue
        if ch in ("þ",):
            out.append("th")
            continue
        if ch in ("Ł",):
            out.append("L")
            continue
        if ch in ("ł",):
            out.append("l")
            continue
        if ch in ("Đ",):
            out.append("D")
            continue
        if ch in ("đ",):
            out.append("d")
            continue
        if ch in ("Ħ",):
            out.append("H")
            continue
        if ch in ("ħ",):
            out.append("h")
            continue
        if ch in ("Ŋ",):
            out.append("N")
            continue
        if ch in ("ŋ",):
            out.append("n")
            continue
        if ch in ("Ĳ",):
            out.append("IJ")
            continue
        if ch in ("ĳ",):
            out.append("ij")
            continue

        name = unicodedata.name(ch, "")
        if name.startswith("LATIN ") and " LETTER " in name:
            out.append("?")
        else:
            out.append("?")

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

    text = _ASCII_APOSTROPHE_TO_SEP_RE.sub(DEFAULT_SEPARATOR, text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        hook = globals().get("unidecode")
        try:
            value = hook(text)
        except Exception:
            value = text
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
        def _ent_repl(m):
            name = m.group(1)
            cp = html.entities.name2codepoint.get(name)
            if cp is None:
                return m.group(0)
            try:
                return chr(cp)
            except Exception:
                return m.group(0)

        text = re.sub(ENTITY_PATTERN, _ent_repl, text)

    if decimal:
        try:
            def _dec_repl(m):
                return chr(int(m.group(1), 10))
            text = re.sub(DECIMAL_PATTERN, _dec_repl, text)
        except Exception:
            pass

    if hexadecimal:
        try:
            def _hex_repl(m):
                return chr(int(m.group(1), 16))
            text = re.sub(HEX_PATTERN, _hex_repl, text)
        except Exception:
            pass

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)

    if lowercase:
        text = text.lower()

    text = _ASCII_APOSTROPHE_REMOVE_RE.sub("", text)
    text = _COMMA_BETWEEN_DIGITS_RE.sub("", text)

    if regex_pattern is not None:
        pattern = regex_pattern
    else:
        if allow_unicode:
            pattern = r"[\W_]+"
        else:
            pattern = r"[^-a-zA-Z0-9]+"

    text = re.sub(pattern, DEFAULT_SEPARATOR, text)

    esc_sep = re.escape(DEFAULT_SEPARATOR)
    text = re.sub(rf"{esc_sep}{{2,}}", DEFAULT_SEPARATOR, text)
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
