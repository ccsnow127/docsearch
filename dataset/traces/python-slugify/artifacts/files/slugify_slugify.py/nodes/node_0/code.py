import re
import unicodedata
import html.entities
from typing import Iterable

try:
    import unidecode  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    unidecode = None  # type: ignore

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
        return string[:max_length].strip(separator)

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
        truncated = string[:max_length]

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

    if not isinstance(text, str):
        text = str(text, "utf-8", "ignore")

    text = re.sub(r"'+", DEFAULT_SEPARATOR, text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        if unidecode is not None:
            text = unidecode.unidecode(text)
        else:
            text = text.encode("ascii", "ignore").decode("ascii")

    if not isinstance(text, str):
        text = str(text, "utf-8", "ignore")

    if entities:
        def _entity_repl(m: re.Match[str]) -> str:
            name = m.group(1)
            cp = html.entities.name2codepoint.get(name)
            return chr(cp) if cp is not None else m.group(0)

        text = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", _entity_repl, text)

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

    if allow_unicode:
        pattern = regex_pattern if regex_pattern is not None else r"[\W_]+"
    else:
        pattern = regex_pattern if regex_pattern is not None else r"[^-a-zA-Z0-9]+"

    text = re.sub(pattern, DEFAULT_SEPARATOR, text)

    text = re.sub(re.escape(DEFAULT_SEPARATOR) + r"{2,}", DEFAULT_SEPARATOR, text)
    text = text.strip(DEFAULT_SEPARATOR)

    if stopwords:
        words = text.split(DEFAULT_SEPARATOR)
        if lowercase:
            stopwords_lower = [w.lower() for w in stopwords]
            words = [w for w in words if w not in stopwords_lower]
        else:
            words = [w for w in words if w not in stopwords]
        text = DEFAULT_SEPARATOR.join(words)

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if max_length > 0:
        text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)

    if separator != DEFAULT_SEPARATOR:
        text = text.replace(DEFAULT_SEPARATOR, separator)

    return text
