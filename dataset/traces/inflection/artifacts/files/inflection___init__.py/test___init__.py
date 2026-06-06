import importlib
import re

import pytest


inflection = importlib.import_module("__init__")


def test__irregular__case_insensitive_same_first_letter_rules_added():
    # Use a unique irregular pair to avoid depending on existing rules.
    before_plurals = list(inflection.PLURALS)
    before_singulars = list(inflection.SINGULARS)

    inflection._irregular("tooth", "teeth")

    # Should insert rules at the front
    assert len(inflection.PLURALS) == len(before_plurals) + 6
    assert len(inflection.SINGULARS) == len(before_singulars) + 2

    # Verify pluralization and singularization work for different cases
    assert inflection.pluralize("tooth") == "teeth"
    assert inflection.pluralize("Tooth") == "Teeth"
    assert inflection.singularize("teeth") == "tooth"
    assert inflection.singularize("Teeth") == "Tooth"


def test__irregular__different_first_letter_rules_added():
    before_plurals = list(inflection.PLURALS)
    before_singulars = list(inflection.SINGULARS)

    inflection._irregular("goose", "geese")

    assert len(inflection.PLURALS) == len(before_plurals) + 4
    assert len(inflection.SINGULARS) == len(before_singulars) + 2

    assert inflection.pluralize("goose") == "geese"
    assert inflection.pluralize("Goose") == "Geese"
    assert inflection.singularize("geese") == "goose"
    assert inflection.singularize("Geese") == "Goose"


def test_camelize_camelize_upper_and_lower_first_letter():
    assert inflection.camelize("device_type") == "DeviceType"
    assert inflection.camelize("device_type", uppercase_first_letter=False) == "deviceType"


def test_dasherize_dasherize_replaces_underscores():
    assert inflection.dasherize("puni_puni") == "puni-puni"


def test_humanize_humanize_strips_id_and_formats():
    assert inflection.humanize("employee_salary") == "Employee salary"
    assert inflection.humanize("author_id") == "Author"


def test_ordinal_ordinal_special_cases_and_negative():
    assert inflection.ordinal(1) == "st"
    assert inflection.ordinal(2) == "nd"
    assert inflection.ordinal(3) == "rd"
    assert inflection.ordinal(4) == "th"
    assert inflection.ordinal(11) == "th"
    assert inflection.ordinal(12) == "th"
    assert inflection.ordinal(13) == "th"
    assert inflection.ordinal(112) == "th"
    assert inflection.ordinal(-1021) == "st"


def test_ordinalize_ordinalize_combines_number_and_suffix():
    assert inflection.ordinalize(1002) == "1002nd"
    assert inflection.ordinalize(-11) == "-11th"


def test_parameterize_parameterize_transliterates_and_separators():
    assert inflection.parameterize("Donald E. Knuth") == "donald-e-knuth"
    # Multiple separators collapse and are stripped from ends
    assert inflection.parameterize("  Hello---world  ", separator="-") == "hello-world"
    # Empty separator: should just remove non allowed chars and lowercase
    assert inflection.parameterize("Hello, World!", separator="") == "helloworld"


def test_pluralize_pluralize_uncountable_and_irregular_camelcase():
    assert inflection.pluralize("") == ""
    assert inflection.pluralize("sheep") == "sheep"
    assert inflection.pluralize("octopus") == "octopi"
    assert inflection.pluralize("CamelOctopus") == "CamelOctopi"


def test_pluralize_pluralize_no_rule_match_returns_original():
    # If no pluralization rule matches, pluralize returns the original word.
    # Use a string that does not match any of the PLURALS regexes.
    word = "foo"  # does not match any pluralization rule patterns
    assert inflection.pluralize(word) == word


def test_singularize_singularize_uncountable_and_regular_and_camelcase():
    assert inflection.singularize("sheep") == "sheep"
    assert inflection.singularize("posts") == "post"
    assert inflection.singularize("CamelOctopi") == "CamelOctopus"
    # Word that is already singular and not matching rules should return itself
    assert inflection.singularize("word") == "word"


def test_tableize_tableize_underscore_and_pluralize_last_word():
    assert inflection.tableize("RawScaledScorer") == "raw_scaled_scorers"
    assert inflection.tableize("egg_and_ham") == "egg_and_hams"
    assert inflection.tableize("fancyCategory") == "fancy_categories"


def test_titleize_titleize_humanize_and_underscore_integration():
    assert inflection.titleize("man from the boondocks") == "Man From The Boondocks"
    assert inflection.titleize("x-men: the last stand") == "X Men: The Last Stand"
    assert inflection.titleize("TheManWithoutAPast") == "The Man Without A Past"
    assert inflection.titleize("raiders_of_the_lost_ark") == "Raiders Of The Lost Ark"


def test_transliterate_transliterate_drops_non_ascii_and_normalizes():
    assert inflection.transliterate("älämölö") == "alamolo"
    # Characters without ASCII approximation are removed
    assert inflection.transliterate("Ærøskøbing") == "rskbing"


def test_underscore_underscore_handles_acronyms_and_dashes():
    assert inflection.underscore("DeviceType") == "device_type"
    assert inflection.underscore("IOError") == "io_error"
    assert inflection.underscore("X-Men") == "x_men"
