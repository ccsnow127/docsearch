import re
import unicodedata
import html.entities


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
        if word == "":
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

    if truncated == "":
        return string[:max_length]

    return truncated.strip(separator)


def slugify(
    text: str,
    entities: bool = True,
    decimal: bool = True,
    hexadecimal: bool = True,
    max_length: int = 0,
    word_boundary: bool = False,
    separator: str = "-",
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
        text = bytes(text).decode("utf-8", "ignore")
    else:
        text = str(text)

    text = re.sub(r"'+", "-", text)

    if allow_unicode:
        text = unicodedata.normalize("NFKC", text)
    else:
        text = unicodedata.normalize("NFKD", text)
        try:
            from unidecode import unidecode  # type: ignore

            text = unidecode(text)
        except Exception:
            text = text.encode("ascii", "ignore").decode("ascii", "ignore")

    if not isinstance(text, str):
        if isinstance(text, (bytes, bytearray, memoryview)):
            text = bytes(text).decode("utf-8", "ignore")
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

    text = unicodedata.normalize("NFKC" if allow_unicode else "NFKD", text)

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

    text = re.sub(pattern, "-", text)

    esc_sep = re.escape("-")
    text = re.sub(esc_sep + r"{2,}", "-", text)
    text = text.strip("-")

    if stopwords:
        tokens = [t for t in text.split("-") if t != ""]
        if lowercase:
            stopwords_lower = [str(w).lower() for w in stopwords]
            tokens = [w for w in tokens if w not in stopwords_lower]
        else:
            tokens = [w for w in tokens if w not in stopwords]
        text = "-".join(tokens)

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if max_length > 0:
        if word_boundary:
            tokens = [t for t in text.split("-") if t != ""]
            out = []
            for t in tokens:
                if not out:
                    candidate = t
                else:
                    candidate = "-".join(out + [t])
                if len(candidate) <= max_length:
                    out.append(t)
                else:
                    break
            text = "-".join(out)
        else:
            cut = text[:max_length]
            cut = cut.rstrip("-")
            text = cut

    if separator != "-":
        text = text.replace("-", separator)

    return text
