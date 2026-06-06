import html.entities
import re
import unicodedata
from typing import Iterable


# Module-global hook for deterministic transliteration when allow_unicode is False.
# Callers may monkeypatch this symbol at module scope.

def unidecode(value):
    """Deterministic best-effort transliteration hook.

    Default implementation strips combining marks after NFKD normalization and
    applies a small, stable mapping for a few common compatibility characters.
    """

    if isinstance(value, str):
        text = value
    elif isinstance(value, (bytes, bytearray, memoryview)):
        b = value if isinstance(value, bytes) else bytes(value)
        try:
            text = b.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            text = b.decode("utf-8", errors="replace")
    else:
        text = str(value)

    mapping = {
        "ß": "ss",
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
    }

    out = []
    for ch in text:
        if ch in mapping:
            out.append(mapping[ch])
        elif unicodedata.combining(ch):
            continue
        else:
            out.append(ch)
    return "".join(out)


DEFAULT_SEPARATOR = "-"


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
    stopwords: Iterable[str] = (),
    regex_pattern: "re.Pattern[str] | str | None" = None,
    lowercase: bool = True,
    replacements: Iterable[Iterable[str]] = (),
    allow_unicode: bool = False,
) -> str:
    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if isinstance(text, str):
        pass
    elif isinstance(text, (bytes, bytearray, memoryview)):
        b = text if isinstance(text, bytes) else bytes(text)
        try:
            text = b.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            text = b.decode("utf-8", errors="replace")
    else:
        text = str(text)

    text = re.sub(r"'+", DEFAULT_SEPARATOR, text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        text = globals()["unidecode"](text)
        if isinstance(text, str):
            pass
        elif isinstance(text, (bytes, bytearray, memoryview)):
            b = text if isinstance(text, bytes) else bytes(text)
            try:
                text = b.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                text = b.decode("utf-8", errors="replace")
        else:
            text = str(text)

    if entities:
        def _ent(m):
            name = m.group(1)
            cp = html.entities.name2codepoint.get(name)
            return chr(cp) if cp is not None else m.group(0)

        text = re.sub(r"&([^;]+);", _ent, text)

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
        text = globals()["unidecode"](text)
        if isinstance(text, str):
            pass
        elif isinstance(text, (bytes, bytearray, memoryview)):
            b = text if isinstance(text, bytes) else bytes(text)
            try:
                text = b.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                text = b.decode("utf-8", errors="replace")
        else:
            text = str(text)

    if lowercase:
        text = text.lower()

    text = re.sub(r"'+", "", text)

    text = re.sub(r"(?<=\d),(?=\d)", "", text)

    if regex_pattern is not None:
        pattern = regex_pattern
    else:
        pattern = r"[\W_]+" if allow_unicode else r"[^-a-zA-Z0-9]+"

    text = re.sub(pattern, DEFAULT_SEPARATOR, text)

    text = re.sub(r"%s{2,}" % re.escape(DEFAULT_SEPARATOR), DEFAULT_SEPARATOR, text)
    text = text.strip(DEFAULT_SEPARATOR)

    if stopwords:
        words = text.split(DEFAULT_SEPARATOR) if text else []
        if lowercase:
            stopwords_lower = {w.lower() for w in stopwords}
            words = [w for w in words if w and w not in stopwords_lower]
        else:
            stopwords_set = set(stopwords)
            words = [w for w in words if w and w not in stopwords_set]
        text = DEFAULT_SEPARATOR.join(words)

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if max_length > 0:
        text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)

    if separator != DEFAULT_SEPARATOR:
        text = text.replace(DEFAULT_SEPARATOR, separator)

    return text
