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

    if singular[0].upper() == plural[0].upper():
        PLURALS.insert(0, (r"(?i)({}){}$".format(singular[0], singular[1:]), r"\1" + plural[1:]))
        PLURALS.insert(0, (r"(?i)({}){}$".format(plural[0], plural[1:]), r"\1" + plural[1:]))
        SINGULARS.insert(0, (r"(?i)({}){}$".format(plural[0], plural[1:]), r"\1" + singular[1:]))
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
        if re.search(r"(?i)\A%s\Z" % re.escape(str(inflection)), word):
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
