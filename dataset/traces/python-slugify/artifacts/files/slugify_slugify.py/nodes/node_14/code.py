import re
import unicodedata
import html.entities

DEFAULT_SEPARATOR = "-"


def unidecode(value):
    if isinstance(value, str):
        text = value
    elif isinstance(value, (bytes, bytearray, memoryview)):
        try:
            text = bytes(value).decode("utf-8", errors="replace")
        except Exception:
            text = str(value)
    else:
        text = str(value)

    text = unicodedata.normalize("NFKD", text)

    ligatures = {
        "ß": "ss",
        "ẞ": "SS",
        "Æ": "AE",
        "æ": "ae",
        "Œ": "OE",
        "œ": "oe",
        "Ø": "O",
        "ø": "o",
        "Ð": "D",
        "ð": "d",
        "Þ": "Th",
        "þ": "th",
        "Ł": "L",
        "ł": "l",
        "Đ": "D",
        "đ": "d",
        "Ĳ": "IJ",
        "ĳ": "ij",
        "Ŋ": "N",
        "ŋ": "n",
        "ĸ": "k",
        "ſ": "s",
    }

    out = []
    for ch in text:
        if ch in ligatures:
            out.append(ligatures[ch])
            continue
        if unicodedata.combining(ch):
            continue
        code = ord(ch)
        if code < 128:
            out.append(ch)
            continue
        name = unicodedata.name(ch, "")
        if name.startswith("GREEK "):
            greek = {
                "Α": "A",
                "Β": "B",
                "Γ": "G",
                "Δ": "D",
                "Ε": "E",
                "Ζ": "Z",
                "Η": "E",
                "Θ": "Th",
                "Ι": "I",
                "Κ": "K",
                "Λ": "L",
                "Μ": "M",
                "Ν": "N",
                "Ξ": "X",
                "Ο": "O",
                "Π": "P",
                "Ρ": "R",
                "Σ": "S",
                "Τ": "T",
                "Υ": "Y",
                "Φ": "F",
                "Χ": "Ch",
                "Ψ": "Ps",
                "Ω": "O",
                "α": "a",
                "β": "b",
                "γ": "g",
                "δ": "d",
                "ε": "e",
                "ζ": "z",
                "η": "e",
                "θ": "th",
                "ι": "i",
                "κ": "k",
                "λ": "l",
                "μ": "m",
                "ν": "n",
                "ξ": "x",
                "ο": "o",
                "π": "p",
                "ρ": "r",
                "σ": "s",
                "ς": "s",
                "τ": "t",
                "υ": "y",
                "φ": "f",
                "χ": "ch",
                "ψ": "ps",
                "ω": "o",
            }
            mapped = greek.get(ch)
            if mapped is not None:
                out.append(mapped)
                continue
        out.append(ch)

    return "".join(out)


def smart_truncate(
    string: str,
    max_length: int = 0,
    word_boundary: bool = False,
    separator: str = " ",
    save_order: bool = False,
) -> str:
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
        text = unidecode(text)
        if isinstance(text, str):
            pass
        elif isinstance(text, (bytes, bytearray, memoryview)):
            try:
                text = bytes(text).decode("utf-8", errors="replace")
            except Exception:
                text = str(text)
        else:
            text = str(text)

    if entities:
        def _ent(m):
            name = m.group(1)
            cp = html.entities.name2codepoint.get(name)
            return chr(cp) if cp is not None else m.group(0)

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
