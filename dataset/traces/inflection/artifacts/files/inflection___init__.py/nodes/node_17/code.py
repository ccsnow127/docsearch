import re
import unicodedata
from typing import List, Set, Tuple

__all__ = [
    "_irregular",
    "caseinsensitive",
    "camelize",
    "dasherize",
    "humanize",
    "ordinal",
    "ordinalize",
    "parameterize",
    "pluralize",
    "singularize",
    "tableize",
    "titleize",
    "transliterate",
    "underscore",
]

PLURALS: List[Tuple[str, str]] = []
SINGULARS: List[Tuple[str, str]] = []
UNCOUNTABLES: Set[str] = set()


def caseinsensitive(string: str) -> str:
    return "".join(f"[{char}{char.upper()}]" for char in string)


def _irregular(singular: str, plural: str) -> None:
    def caseinsensitive(string: str) -> str:
        return "".join(f"[{c}{c.upper()}]" for c in string)

    same_initial_letter = singular[0].upper() == plural[0].upper()
    same_tail = singular[1:] == plural[1:]
    use_simple_i_flag = same_initial_letter and same_tail

    if use_simple_i_flag:
        PLURALS.insert(
            0,
            (
                r"(?i)({}){}$".format(singular[0], singular[1:]),
                r"\1" + plural[1:],
            ),
        )
        PLURALS.insert(
            0,
            (
                r"(?i)({}){}$".format(plural[0], plural[1:]),
                r"\1" + plural[1:],
            ),
        )
        SINGULARS.insert(
            0,
            (
                r"(?i)({}){}$".format(plural[0], plural[1:]),
                r"\1" + singular[1:],
            ),
        )
    else:
        PLURALS.insert(
            0,
            (
                r"{}{}$".format(singular[0].upper(), caseinsensitive(singular[1:])),
                plural[0].upper() + plural[1:],
            ),
        )
        PLURALS.insert(
            0,
            (
                r"{}{}$".format(singular[0].lower(), caseinsensitive(singular[1:])),
                plural[0].lower() + plural[1:],
            ),
        )
        PLURALS.insert(
            0,
            (
                r"{}{}$".format(plural[0].upper(), caseinsensitive(plural[1:])),
                plural[0].upper() + plural[1:],
            ),
        )
        PLURALS.insert(
            0,
            (
                r"{}{}$".format(plural[0].lower(), caseinsensitive(plural[1:])),
                plural[0].lower() + plural[1:],
            ),
        )

        SINGULARS.insert(
            0,
            (
                r"{}{}$".format(plural[0].upper(), caseinsensitive(plural[1:])),
                singular[0].upper() + singular[1:],
            ),
        )
        SINGULARS.insert(
            0,
            (
                r"{}{}$".format(plural[0].lower(), caseinsensitive(plural[1:])),
                singular[0].lower() + singular[1:],
            ),
        )


def camelize(string: str, uppercase_first_letter: bool = True) -> str:
    if uppercase_first_letter:
        return re.sub(r"(?:^|_)(.)", lambda m: m.group(1).upper(), string)
    camel = camelize(string)
    return string[0].lower() + camel[1:]


def dasherize(word: str) -> str:
    return word.replace("_", "-")


def humanize(word: str) -> str:
    word = re.sub(r"_id$", "", word)
    word = word.replace("_", " ")
    word = re.sub(r"(?i)([a-z\d]*)", lambda m: m.group(1).lower(), word)
    word = re.sub(r"^\w", lambda m: m.group(0).upper(), word)
    return word


def ordinal(number: int) -> str:
    number = abs(int(number))
    if number % 100 in (11, 12, 13):
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")


def ordinalize(number: int) -> str:
    return "{}{}".format(number, ordinal(number))


def transliterate(string: str) -> str:
    normalized = unicodedata.normalize("NFKD", string)
    return normalized.encode("ascii", errors="ignore").decode("ascii")


def parameterize(string: str, separator: str = "-") -> str:
    string = transliterate(string)
    string = re.sub(r"(?i)[^a-z0-9\-_]+", separator, string)
    if separator:
        re_sep = re.escape(separator)
        string = re.sub(r"%s{2,}" % re_sep, separator, string)
        string = re.sub(r"(?i)^{sep}|{sep}$".format(sep=re_sep), "", string)
    return string.lower()


def pluralize(word: str) -> str:
    if not word:
        return word
    lower = word.lower()
    if lower in UNCOUNTABLES:
        return word
    for rule, replacement in PLURALS:
        if re.search(rule, word):
            return re.sub(rule, replacement, word)
    return word


def singularize(word: str) -> str:
    for inflection in UNCOUNTABLES:
        if word.casefold() == str(inflection).casefold():
            return word
    for rule, replacement in SINGULARS:
        if re.search(rule, word):
            return re.sub(rule, replacement, word)
    return word


def underscore(word: str) -> str:
    word = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", word)
    word = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", word)
    word = word.replace("-", "_")
    return word.lower()


def tableize(word: str) -> str:
    return pluralize(underscore(word))


def titleize(word: str) -> str:
    word = underscore(word)
    word = humanize(word)
    word = word.title()
    word = re.sub(r"\b('?\w)", lambda m: m.group(1).capitalize(), word)
    return word


def _initialize_default_inflections() -> None:
    global PLURALS, SINGULARS, UNCOUNTABLES

    UNCOUNTABLES.update(
        {
            "equipment",
            "information",
            "rice",
            "money",
            "species",
            "series",
            "fish",
            "sheep",
            "jeans",
            "police",
            "bison",
            "deer",
            "moose",
            "news",
            "offspring",
            "salmon",
            "shrimp",
            "swine",
            "trout",
            "aircraft",
        }
    )

    # Plural rules (lower precedence added later; we insert irregulars via _irregular)
    PLURALS.extend(
        [
            (r"$", "s"),
            (r"s$", "s"),
            (r"(?i)(ax|test)is$", r"\1es"),
            (r"(?i)(octop|vir)us$", r"\1i"),
            (r"(?i)(alias|status)$", r"\1es"),
            (r"(?i)(bu)s$", r"\1ses"),
            (r"(?i)(buffal|tomat)o$", r"\1oes"),
            (r"(?i)([ti])um$", r"\1a"),
            (r"(?i)sis$", "ses"),
            (r"(?i)(?:([^f])fe|([lr])f)$", r"\1\2ves"),
            (r"(?i)(hive)$", r"\1s"),
            (r"(?i)([^aeiouy]|qu)y$", r"\1ies"),
            (r"(?i)(x|ch|ss|sh)$", r"\1es"),
            (r"(?i)(matr|vert|ind)(?:ix|ex)$", r"\1ices"),
            (r"(?i)([m|l])ouse$", r"\1ice"),
            (r"(?i)^(ox)$", r"\1en"),
            (r"(?i)(quiz)$", r"\1zes"),
        ]
    )

    # Singular rules
    SINGULARS.extend(
        [
            (r"s$", ""),
            (r"(?i)(ss)$", r"\1"),
            (r"(?i)(n)ews$", r"\1ews"),
            (r"(?i)([ti])a$", r"\1um"),
            (r"(?i)((a)naly|(b)a|(d)iagno|(p)arenthe|(p)rogno|(s)ynop|(t)he)ses$", r"\1\2sis"),
            (r"(?i)(^analy)ses$", r"\1sis"),
            (r"(?i)([^f])ves$", r"\1fe"),
            (r"(?i)(hive)s$", r"\1"),
            (r"(?i)(tive)s$", r"\1"),
            (r"(?i)([lr])ves$", r"\1f"),
            (r"(?i)([^aeiouy]|qu)ies$", r"\1y"),
            (r"(?i)(s)eries$", r"\1eries"),
            (r"(?i)(m)ovies$", r"\1ovie"),
            (r"(?i)(x|ch|ss|sh)es$", r"\1"),
            (r"(?i)([m|l])ice$", r"\1ouse"),
            (r"(?i)(bus)es$", r"\1"),
            (r"(?i)(o)es$", r"\1"),
            (r"(?i)(shoe)s$", r"\1"),
            (r"(?i)(cris|ax|test)es$", r"\1is"),
            (r"(?i)(octop|vir)i$", r"\1us"),
            (r"(?i)(alias|status)es$", r"\1"),
            (r"(?i)^(ox)en$", r"\1"),
            (r"(?i)(vert|ind)ices$", r"\1ex"),
            (r"(?i)(matr)ices$", r"\1ix"),
            (r"(?i)(quiz)zes$", r"\1"),
            (r"(?i)(database)s$", r"\1"),
        ]
    )

    # Irregulars (prepend for precedence)
    for s, p in [
        ("person", "people"),
        ("man", "men"),
        ("child", "children"),
        ("sex", "sexes"),
        ("move", "moves"),
        ("mouse", "mice"),
        ("goose", "geese"),
        ("foot", "feet"),
        ("tooth", "teeth"),
        ("ox", "oxen"),
        ("louse", "lice"),
        ("die", "dice"),
    ]:
        _irregular(s, p)


_initialize_default_inflections()
