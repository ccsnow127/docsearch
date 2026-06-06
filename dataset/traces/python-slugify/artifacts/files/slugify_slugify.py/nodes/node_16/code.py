DEFAULT_SEPARATOR = '-'

def unidecode(value):
    if isinstance(value, str):
        text = value
    elif isinstance(value, (bytes, bytearray, memoryview)):
        text = bytes(value).decode("utf-8", errors="replace")
    else:
        text = str(value)

    text = text.replace("ß", "ss").replace("ẞ", "SS")
    text = text.replace("Æ", "AE").replace("æ", "ae")
    text = text.replace("Œ", "OE").replace("œ", "oe")
    text = text.replace("Ø", "O").replace("ø", "o")
    text = text.replace("Ð", "D").replace("ð", "d")
    text = text.replace("Þ", "Th").replace("þ", "th")
    text = text.replace("Ł", "L").replace("ł", "l")
    text = text.replace("Đ", "D").replace("đ", "d")
    text = text.replace("Ĳ", "IJ").replace("ĳ", "ij")
    text = text.replace("ŉ", "n")

    try:
        import unicodedata as _ud  # noqa: F401
    except Exception:
        _ud = None

    if _ud is None:
        out = []
        for ch in text:
            o = ord(ch)
            if o < 128:
                out.append(ch)
            else:
                out.append("")
        return "".join(out)

    decomposed = _ud.normalize("NFKD", text)
    out = []
    for ch in decomposed:
        if _ud.combining(ch):
            continue
        o = ord(ch)
        if o < 128:
            out.append(ch)
        else:
            out.append("")
    return "".join(out)


def smart_truncate(string: str, max_length: int = 0, word_boundary: bool = False, separator: str = ' ', save_order: bool = False) -> str:
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

    truncated = ''
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
    try:
        import re as _re  # noqa: F401
    except Exception:
        _re = None
    try:
        import unicodedata as _ud  # noqa: F401
    except Exception:
        _ud = None
    try:
        import html.entities as _html_entities  # noqa: F401
    except Exception:
        _html_entities = None

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if isinstance(text, str):
        pass
    elif isinstance(text, (bytes, bytearray, memoryview)):
        text = bytes(text).decode("utf-8", errors="replace")
    else:
        text = str(text)

    if _re is None:
        # Minimal fallback without regex support: do best-effort deterministic cleanup.
        if lowercase:
            text = text.lower()
        # Replace apostrophes with separator early and remove later
        text = text.replace("'", DEFAULT_SEPARATOR)
        if _ud is not None:
            text = _ud.normalize("NFKC" if allow_unicode else "NFKD", text)
        if not allow_unicode:
            text = globals()["unidecode"](text)
            if isinstance(text, (bytes, bytearray, memoryview)):
                text = bytes(text).decode("utf-8", errors="replace")
            elif not isinstance(text, str):
                text = str(text)
        # crude cleanup: keep alnum (and unicode alnum if allow_unicode), else separator
        out = []
        for ch in text:
            if ch == "'":
                continue
            if ch.isalnum() or (allow_unicode and ch.isalpha()):
                out.append(ch)
            else:
                out.append(DEFAULT_SEPARATOR)
        text = "".join(out)
        while DEFAULT_SEPARATOR * 2 in text:
            text = text.replace(DEFAULT_SEPARATOR * 2, DEFAULT_SEPARATOR)
        text = text.strip(DEFAULT_SEPARATOR)
        if stopwords:
            parts = [p for p in text.split(DEFAULT_SEPARATOR) if p]
            if lowercase:
                sw = set(str(w).lower() for w in stopwords)
                parts = [p for p in parts if p not in sw]
            else:
                sw = set(stopwords)
                parts = [p for p in parts if p not in sw]
            text = DEFAULT_SEPARATOR.join(parts)
        if replacements:
            for old, new in replacements:
                text = text.replace(old, new)
        if max_length > 0:
            text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)
        if separator != DEFAULT_SEPARATOR:
            text = text.replace(DEFAULT_SEPARATOR, separator)
        return text

    text = _re.sub(r"'+", DEFAULT_SEPARATOR, text)

    if _ud is not None:
        text = _ud.normalize("NFKC" if allow_unicode else "NFKD", text)

    if not allow_unicode:
        u = globals()["unidecode"](text)
        if isinstance(u, str):
            text = u
        elif isinstance(u, (bytes, bytearray, memoryview)):
            text = bytes(u).decode("utf-8", errors="replace")
        else:
            text = str(u)

    if entities and _html_entities is not None:
        name2cp = _html_entities.name2codepoint

        def _ent(m):
            name = m.group(1)
            cp = name2cp.get(name)
            if cp is None:
                return m.group(0)
            try:
                return chr(cp)
            except Exception:
                return m.group(0)

        text = _re.sub(r"&([A-Za-z][A-Za-z0-9]+);", _ent, text)

    if decimal:
        try:
            text = _re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
        except Exception:
            pass

    if hexadecimal:
        try:
            text = _re.sub(r"&#x([\da-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
        except Exception:
            pass

    if _ud is not None:
        text = _ud.normalize("NFKC" if allow_unicode else "NFKD", text)

    if lowercase:
        text = text.lower()

    text = _re.sub(r"'+", "", text)

    text = _re.sub(r"(?<=\d),(?=\d)", "", text)

    if regex_pattern is not None:
        pattern = regex_pattern
    else:
        if allow_unicode:
            pattern = r"[\W_]+"
        else:
            pattern = r"[^-a-zA-Z0-9]+"

    text = _re.sub(pattern, DEFAULT_SEPARATOR, text)

    esc_sep = _re.escape(DEFAULT_SEPARATOR)
    text = _re.sub(esc_sep + r"{2,}", DEFAULT_SEPARATOR, text)
    text = text.strip(DEFAULT_SEPARATOR)

    if stopwords:
        tokens = [w for w in text.split(DEFAULT_SEPARATOR) if w]
        if lowercase:
            stopwords_lower = set(str(w).lower() for w in stopwords)
            tokens = [w for w in tokens if w not in stopwords_lower]
        else:
            stopwords_set = set(stopwords)
            tokens = [w for w in tokens if w not in stopwords_set]
        text = DEFAULT_SEPARATOR.join(tokens)

    if replacements:
        for old, new in replacements:
            text = text.replace(old, new)

    if max_length > 0:
        text = smart_truncate(text, max_length, word_boundary, DEFAULT_SEPARATOR, save_order)

    if separator != DEFAULT_SEPARATOR:
        text = text.replace(DEFAULT_SEPARATOR, separator)

    return text
