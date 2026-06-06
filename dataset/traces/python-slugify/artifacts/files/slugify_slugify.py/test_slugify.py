import pytest

import slugify as slugify_module


def test_smart_truncate_smart_truncate_no_max_length_strips_separator():
    assert slugify_module.smart_truncate("  hello  ", max_length=0, separator=" ") == "hello"


def test_smart_truncate_smart_truncate_shorter_than_max_returns_stripped():
    assert slugify_module.smart_truncate("--hi--", max_length=10, separator="-") == "hi"


def test_smart_truncate_smart_truncate_no_word_boundary_simple_cut():
    assert slugify_module.smart_truncate("hello world", max_length=5, word_boundary=False, separator=" ") == "hello"


def test_smart_truncate_smart_truncate_word_boundary_no_separator_in_string():
    assert slugify_module.smart_truncate("helloworld", max_length=5, word_boundary=True, separator=" ") == "hello"


def test_smart_truncate_smart_truncate_word_boundary_builds_words():
    # Fits "hello" but not "world" when max_length=6 (would require space)
    assert slugify_module.smart_truncate("hello world", max_length=6, word_boundary=True, separator=" ") == "hello"


def test_smart_truncate_smart_truncate_word_boundary_save_order_breaks_early():
    # "aa" fits, "bbbb" doesn't; with save_order=True we stop and do not include later short words
    assert (
        slugify_module.smart_truncate("aa bbbb c", max_length=4, word_boundary=True, separator=" ", save_order=True)
        == "aa"
    )


def test_smart_truncate_smart_truncate_word_boundary_without_save_order_skips_long_word():
    # Without save_order, long word is skipped and later short word can be included
    assert (
        slugify_module.smart_truncate("aa bbbb c", max_length=4, word_boundary=True, separator=" ", save_order=False)
        == "aa c"
    )


def test_smart_truncate_smart_truncate_word_boundary_first_word_too_long_fallback():
    # If no word can be added, falls back to raw slice
    assert slugify_module.smart_truncate("abcdefgh ij", max_length=3, word_boundary=True, separator=" ") == "abc"


def test_smart_truncate_smart_truncate_word_boundary_all_words_too_long_fallback():
    # When every split token is longer than max_length, loop adds nothing and fallback triggers.
    assert slugify_module.smart_truncate("abcd efgh", max_length=3, word_boundary=True, separator=" ") == "abc"


def test_slugify_slugify_basic_ascii_and_lowercase_default():
    assert slugify_module.slugify("Hello, World!") == "hello-world"


def test_slugify_slugify_replacements_applied_pre_and_post():
    # Pre: replace '&' with 'and' before entity conversion; Post: replace '-' with '_' after slug creation
    out = slugify_module.slugify("Tom & Jerry", replacements=(("&", "and"), ("-", "_")))
    assert out == "tom_and_jerry"


def test_slugify_slugify_html_entities_decimal_hexadecimal_converted():
    text = "Fish &amp; Chips &#38; Salsa &#x26; Guac"
    assert slugify_module.slugify(text) == "fish-chips-salsa-guac"


def test_slugify_slugify_decimal_invalid_is_ignored_gracefully():
    # Malformed decimal entity should not be converted; it will be cleaned into tokens.
    text = "bad &#notanumber; entity"
    assert slugify_module.slugify(text, decimal=True) == "bad-notanumber-entity"


def test_slugify_slugify_hex_invalid_is_ignored_gracefully():
    text = "bad &#xZZ; entity"
    assert slugify_module.slugify(text, hexadecimal=True) == "bad-xzz-entity"


def test_slugify_slugify_decimal_exception_path_is_swallowed(monkeypatch):
    # Force the DECIMAL_PATTERN.sub call to raise, exercising the try/except.
    class BoomPattern:
        def sub(self, repl, text):
            raise ValueError("boom")

    monkeypatch.setattr(slugify_module, "DECIMAL_PATTERN", BoomPattern())
    assert slugify_module.slugify("a &#123; b", decimal=True) == "a-123-b"


def test_slugify_slugify_hex_exception_path_is_swallowed(monkeypatch):
    class BoomPattern:
        def sub(self, repl, text):
            raise ValueError("boom")

    monkeypatch.setattr(slugify_module, "HEX_PATTERN", BoomPattern())
    assert slugify_module.slugify("a &#x26; b", hexadecimal=True) == "a-x26-b"


def test_slugify_slugify_non_str_input_is_decoded_from_utf8_bytes():
    assert slugify_module.slugify("Caf\xc3\xa9".encode("utf-8")) == "cafe"


def test_slugify_slugify_unidecode_returning_bytes_is_decoded(monkeypatch):
    # Exercise the second "ensure text is still in unicode" branch by making unidecode return bytes.
    monkeypatch.setattr(slugify_module.unidecode, "unidecode", lambda s: b"BYTES")
    assert slugify_module.slugify("anything", allow_unicode=False) == "bytes"


def test_smart_truncate_smart_truncate_word_boundary_exact_length_includes_word():
    assert slugify_module.smart_truncate("aa bb", max_length=5, word_boundary=True, separator=" ") == "aa bb"


def test_slugify_slugify_allow_unicode_keeps_unicode_letters():
    assert slugify_module.slugify("Zażółć gęślą", allow_unicode=True) == "zażółć-gęślą"


def test_slugify_slugify_disallow_unicode_transliterates():
    assert slugify_module.slugify("Zażółć gęślą", allow_unicode=False) == "zazolc-gesla"


def test_slugify_slugify_custom_separator_replaces_default():
    assert slugify_module.slugify("a b c", separator="_") == "a_b_c"


def test_slugify_slugify_stopwords_lowercase_true_removes_case_insensitive():
    assert slugify_module.slugify("The Quick Brown Fox", stopwords=("the", "FOX")) == "quick-brown"


def test_slugify_slugify_stopwords_lowercase_false_is_case_sensitive():
    assert slugify_module.slugify("The the", lowercase=False, stopwords=("The",)) == "the"


def test_slugify_slugify_regex_pattern_override_changes_cleanup():
    # Allow dots to remain by only replacing spaces
    assert slugify_module.slugify("a.b c", regex_pattern=r"\s+") == "a.b-c"


def test_slugify_slugify_numbers_cleanup_removes_thousands_separator_commas():
    assert slugify_module.slugify("Price 1,234,567 USD") == "price-1234567-usd"


def test_slugify_slugify_quotes_turn_into_word_separators_then_removed():
    # Quotes become dashes, then removed, leaving separation between words
    assert slugify_module.slugify("rock'n'roll") == "rock-n-roll"


def test_slugify_slugify_max_length_truncates_with_word_boundary_and_save_order():
    # slug becomes 'one-two-three'; with max_length=7 and word_boundary True -> 'one-two'
    assert slugify_module.slugify("one two three", max_length=7, word_boundary=True) == "one-two"
