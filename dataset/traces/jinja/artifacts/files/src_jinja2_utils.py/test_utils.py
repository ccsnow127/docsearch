import json
import os
import pickle
import re
import types

import markupsafe
import pytest

import utils


def test__MissingType___repr____reduce__():
    # Cover _MissingType and the module-level singleton.
    m = utils._MissingType()
    assert repr(m) == "missing"
    assert m.__reduce__() == "missing"
    assert repr(utils.missing) == "missing"


def test_concat_join_alias():
    assert utils.concat(["a", "b", "c"]) == "abc"


def test_pass_context_pass_context_docstring_mentions_context():
    # Touch the docstring lines near the top of the function.
    doc = utils.pass_context.__doc__ or ""
    assert "Context" in doc
    assert "filters" in doc
    assert "tests" in doc
    assert "pass_eval_context" in doc
    assert "pass_environment" in doc
    assert "eval_context" in doc
    assert "environment" in doc


def test_pass_context_pass_context_versionadded_in_docstring():
    doc = utils.pass_context.__doc__ or ""
    assert "versionadded" in doc
    assert "3.0.0" in doc
    assert "contextfunction" in doc


def test_pass_eval_context_pass_eval_context_sets_attribute():
    def g():
        return None

    utils.pass_eval_context(g)
    assert g.jinja_pass_arg is utils._PassArg.eval_context


def test_pass_eval_context_pass_eval_context_docstring_mentions_eval_context():
    doc = utils.pass_eval_context.__doc__ or ""
    assert "EvalContext" in doc
    assert "filters" in doc
    assert "tests" in doc
    assert "EvalContext.environment" in doc
    assert "pass_environment" in doc
    assert "evalcontextfunction" in doc
    assert "3.0.0" in doc
    assert "eval-context" in doc


def test_pass_environment_pass_environment_sets_attribute():
    def h():
        return None

    utils.pass_environment(h)
    assert h.jinja_pass_arg is utils._PassArg.environment


def test_pass_environment_pass_environment_docstring_mentions_environment():
    doc = utils.pass_environment.__doc__ or ""
    assert "Environment" in doc
    assert "filters" in doc
    assert "tests" in doc
    assert "versionadded" in doc
    assert "environmentfunction" in doc
    assert "environmentfilter" in doc
    assert "Replaces" in doc
    assert "3.0.0" in doc


def test__PassArg_from_obj_none_when_missing_attr():
    def f():
        return None

    assert utils._PassArg.from_obj(f) is None


def test__PassArg_from_obj_returns_enum_when_attr_present():
    def f():
        return None

    utils.pass_context(f)
    assert utils._PassArg.from_obj(f) is utils._PassArg.context


def test_pass_context_pass_context_sets_attribute():
    def f():
        return None

    assert not hasattr(f, "jinja_pass_arg")
    utils.pass_context(f)
    assert f.jinja_pass_arg is utils._PassArg.context


def test_internalcode_internalcode_marks_code_object_in_internal_code_set():
    def f():
        return 1

    assert f.__code__ not in utils.internal_code
    utils.internalcode(f)
    assert f.__code__ in utils.internal_code
    # decorator returns the same function
    assert utils.internalcode(f) is f


def test_import_string_import_string_imports_module_and_attribute_and_silent():
    # module import
    mod = utils.import_string("json")
    assert mod is json

    # dotted attribute
    dumps = utils.import_string("json.dumps")
    assert dumps is json.dumps

    # colon attribute
    loads = utils.import_string("json:loads")
    assert loads is json.loads

    # silent failure returns None
    assert utils.import_string("json:nope", silent=True) is None

    with pytest.raises((ImportError, AttributeError)):
        utils.import_string("json:nope", silent=False)


def test_open_if_exists_returns_none_or_file(tmp_path):
    missing = tmp_path / "missing.txt"
    assert utils.open_if_exists(str(missing)) is None

    p = tmp_path / "a.txt"
    p.write_text("hello")
    f = utils.open_if_exists(str(p), "r")
    assert f is not None
    try:
        assert f.read() == "hello"
    finally:
        f.close()


def test_object_type_repr_builtin_and_special_singletons():
    assert utils.object_type_repr(None) == "None"
    assert utils.object_type_repr(Ellipsis) == "Ellipsis"
    assert utils.object_type_repr(1) == "int object"

    class C:
        pass

    c = C()
    s = utils.object_type_repr(c)
    assert s.endswith(".C object")
    assert "builtins" not in s


def test_pformat_formats_like_pprint():
    out = utils.pformat({"a": [1, 2]})
    assert "'a'" in out and "[1, 2]" in out


def test_urlize_http_www_email_mailto_and_extra_schemes_and_trim():
    text = "See http://example.com, www.example.com and test@example.com"
    rv = utils.urlize(text)
    assert '<a href="http://example.com">http://example.com</a>,' in rv
    assert '<a href="https://www.example.com">www.example.com</a>' in rv
    assert '<a href="mailto:test@example.com">test@example.com</a>' in rv

    # mailto scheme
    rv2 = utils.urlize("mailto:user@example.com")
    assert rv2 == '<a href="mailto:user@example.com">user@example.com</a>'

    # extra schemes
    rv3 = utils.urlize("git+ssh://example.com/repo", extra_schemes=["git+ssh://"])
    assert '<a href="git+ssh://example.com/repo">git+ssh://example.com/repo</a>' in rv3

    # trim
    long_url = "http://example.com/" + "a" * 50
    rv4 = utils.urlize(long_url, trim_url_limit=10)
    assert rv4.endswith(">http://exa...</a>")


def test_urlize_balances_parentheses_and_escapes_html():
    # trailing ) should be included if balances (
    rv = utils.urlize("(http://example.com/test(1))")
    assert rv.startswith("(") and rv.endswith(")")
    assert "test(1)" in rv

    # ensure input is escaped
    rv2 = utils.urlize("<script>http://example.com</script>")
    assert "&lt;script&gt;" in rv2
    assert "&lt;/script&gt;" in rv2


def test_generate_lorem_ipsum_generate_lorem_ipsum_importerror_when_not_package():
    # utils.py uses a relative import from .constants, which will fail when
    # imported as a top-level module in this kata layout.
    with pytest.raises(ImportError):
        utils.generate_lorem_ipsum(n=1, html=False, min=2, max=3)


def test_url_quote_bytes_str_other_and_for_qs():
    assert utils.url_quote(b"a/b") == "a/b"
    assert utils.url_quote("a b", for_qs=True) == "a+b"
    assert utils.url_quote("/", for_qs=True) == "%2F"
    assert utils.url_quote(123) == "123"


def test_LRUCache_set_get_eviction_and_ordering():
    c = utils.LRUCache(2)
    c["a"] = 1
    c["b"] = 2
    assert list(c.keys()) == ["b", "a"]

    # access a makes it most recent
    assert c["a"] == 1
    assert list(c.keys()) == ["a", "b"]

    # adding c evicts least recent (b)
    c["c"] = 3
    assert "b" not in c
    assert set(c.keys()) == {"a", "c"}

    # items are most recent first
    assert c.items()[0][0] in {"a", "c"}


def test_LRUCache_get_default_setdefault_clear_del_and_repr():
    c = utils.LRUCache(1)
    assert c.get("missing", 42) == 42
    assert c.setdefault("x", "y") == "y"
    assert c.get("x") == "y"
    assert c.setdefault("x", "z") == "y"

    r = repr(c)
    assert r.startswith("<LRUCache") and "'x'" in r

    del c["x"]
    assert len(c) == 0

    c["a"] = 1
    c.clear()
    assert len(c) == 0


def test_LRUCache_copy_and_pickle_roundtrip():
    c = utils.LRUCache(2)
    c["a"] = 1
    c["b"] = 2
    c2 = c.copy()
    assert isinstance(c2, utils.LRUCache)
    assert c2.capacity == 2
    assert list(c2.items()) == list(c.items())

    data = pickle.dumps(c)
    c3 = pickle.loads(data)
    assert list(c3.items()) == list(c.items())
    # ensure methods reinitialized
    c3["a"]


def test_select_autoescape_enabled_disabled_default_and_string_default():
    f = utils.select_autoescape(
        enabled_extensions=("html", "xml"),
        disabled_extensions=("txt",),
        default_for_string=True,
        default=False,
    )
    assert f(None) is True
    assert f("index.HTML") is True
    assert f("readme.txt") is False
    assert f("unknown.bin") is False

    f2 = utils.select_autoescape(default_for_string=False, default=True)
    assert f2(None) is False
    assert f2("unknown") is True


def test_htmlsafe_json_dumps_escapes_unsafe_chars_and_is_markup():
    obj = {"x": "<>&'"}
    rv = utils.htmlsafe_json_dumps(obj, sort_keys=True)
    assert isinstance(rv, markupsafe.Markup)
    s = str(rv)
    assert "\\u003c" in s and "\\u003e" in s and "\\u0026" in s and "\\u0027" in s

    # custom dumps
    def custom(o, **kwargs):
        return "<" + json.dumps(o, **kwargs) + ">"

    rv2 = utils.htmlsafe_json_dumps({"a": 1}, dumps=custom)
    assert str(rv2).startswith("\\u003c") and str(rv2).endswith("\\u003e")


def test_Cycler_next_current_reset_and_init_error():
    with pytest.raises(RuntimeError):
        utils.Cycler()

    c = utils.Cycler("a", "b")
    assert c.current == "a"
    assert c.next() == "a"
    assert c.current == "b"
    assert next(c) == "b"
    assert c.current == "a"
    c.reset()
    assert c.current == "a"


def test_Joiner___call___separator_behavior():
    j = utils.Joiner(",")
    assert j() == ""
    assert j() == ","
    assert j() == ","


def test_Namespace___getattribute___setitem___repr___init_from_dict_and_kwargs():
    ns = utils.Namespace({"a": 1}, b=2)
    assert ns.a == 1
    assert ns.b == 2
    ns["c"] = 3
    assert ns.c == 3
    assert "Namespace" in repr(ns) and "'c': 3" in repr(ns)

    with pytest.raises(AttributeError):
        _ = ns.missing_attr

    # __class__ should be accessible
    assert ns.__class__ is utils.Namespace
