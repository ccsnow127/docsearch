import re
import unicodedata
import html.entities
from typing import Iterable

DEFAULT_SEPARATOR = "-"

ENTITY_PATTERN = re.compile(r"&(?P<name>[A-Za-z0-9]+);")
DECIMAL_PATTERN = re.compile(r"&#(?P<code>[0-9]+);")
HEX_PATTERN = re.compile(r"&#[xX](?P<code>[0-9A-Fa-f]+);")


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
    stopwords: Iterable[str] = (),
    regex_pattern: re.Pattern[str] | str | None = None,
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
        text = b.decode("utf-8", errors="replace")
    else:
        text = str(text)

    text = re.sub(r"'+", DEFAULT_SEPARATOR, text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.encode("ascii", "ignore").decode("ascii")

    if not isinstance(text, str):
        if isinstance(text, (bytes, bytearray, memoryview)):
            b = text if isinstance(text, bytes) else bytes(text)
            text = b.decode("utf-8", errors="replace")
        else:
            text = str(text)

    if entities:
        def _ent_repl(m: re.Match[str]) -> str:
            name = m.groupdict().get("name") if m.groupdict() else None
            if not name:
                try:
                    name = m.group(1)
                except Exception:
                    name = None
            if not name:
                return m.group(0)
            cp = html.entities.name2codepoint.get(name)
            if cp is None:
                return m.group(0)
            try:
                return chr(cp)
            except Exception:
                return m.group(0)

        text = ENTITY_PATTERN.sub(_ent_repl, text)

    if decimal:
        try:
            def _dec_repl(m: re.Match[str]) -> str:
                code = m.groupdict().get("code") if m.groupdict() else None
                if not code:
                    code = m.group(1)
                return chr(int(code, 10))

            text = DECIMAL_PATTERN.sub(_dec_repl, text)
        except Exception:
            pass

    if hexadecimal:
        try:
            def _hex_repl(m: re.Match[str]) -> str:
                code = m.groupdict().get("code") if m.groupdict() else None
                if not code:
                    code = m.group(1)
                return chr(int(code, 16))

            text = HEX_PATTERN.sub(_hex_repl, text)
        except Exception:
            pass

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.encode("ascii", "ignore").decode("ascii")

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
