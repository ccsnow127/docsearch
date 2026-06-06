from __future__ import annotations

import abc
import collections.abc
import enum
import json
import os
import random
import re
import typing as t
from collections import deque
from copy import copy
from threading import Lock
from urllib.parse import quote_from_bytes

import typing_extensions as te
from markupsafe import Markup, escape

F = t.TypeVar("F", bound=t.Any)

internal_code: set[t.Any] = set()


class _MissingType:
    def __repr__(self) -> str:
        return "missing"

    def __reduce__(self) -> str:
        return "missing"


missing = _MissingType()


class _PassArg(enum.Enum):
    context = enum.auto()
    eval_context = enum.auto()
    environment = enum.auto()

    @classmethod
    def from_obj(cls, obj: F) -> t.Optional["_PassArg"]:
        if hasattr(obj, "jinja_pass_arg"):
            return t.cast(t.Any, obj).jinja_pass_arg
        return None


def pass_context(f: F) -> F:
    t.cast(t.Any, f).jinja_pass_arg = _PassArg.context
    return f


def pass_eval_context(f: F) -> F:
    t.cast(t.Any, f).jinja_pass_arg = _PassArg.eval_context
    return f


def pass_environment(f: F) -> F:
    t.cast(t.Any, f).jinja_pass_arg = _PassArg.environment
    return f


def internalcode(f: F) -> F:
    internal_code.add(t.cast(t.Any, f).__code__)
    return f


def is_undefined(obj: t.Any) -> bool:
    from .runtime import Undefined  # type: ignore

    return isinstance(obj, Undefined)


def consume(iterable: t.Iterable[t.Any]) -> None:
    for _ in iterable:
        pass


def clear_caches() -> None:
    from jinja2.environment import get_spontaneous_environment
    from jinja2.lexer import _lexer_cache

    get_spontaneous_environment.cache_clear()
    _lexer_cache.clear()


def import_string(import_name: str, silent: bool = False) -> t.Any:
    try:
        if ":" in import_name:
            module, obj = import_name.split(":", 1)
        elif "." in import_name:
            module, _, obj = import_name.rpartition(".")
        else:
            return __import__(import_name)

        mod = __import__(module, None, None, [obj])
        return getattr(mod, obj)
    except (ImportError, AttributeError):
        if not silent:
            raise
        return None


def open_if_exists(filename: str, mode: str = "rb") -> t.IO[t.Any] | None:
    if not os.path.isfile(filename):
        return None
    return open(filename, mode)


def object_type_repr(obj: t.Any) -> str:
    if obj is None:
        return "None"
    if obj is Ellipsis:
        return "Ellipsis"

    cls = type(obj)

    if cls.__module__ == "builtins":
        return f"{cls.__name__} object"

    return f"{cls.__module__}.{cls.__name__} object"


def pformat(obj: t.Any) -> str:
    from pprint import pformat as _pformat

    return _pformat(obj)


_email_re = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)

_http_re = re.compile(
    r"^(?:https?://|www\.)"
    r"(?:[^\s<>()]+|\([^\s<>()]*\))+"
    r"(?:[^\s<>()]*[^\s<>().,])?$",
    re.IGNORECASE,
)


def urlize(
    text: str,
    trim_url_limit: int | None = None,
    rel: str | None = None,
    target: str | None = None,
    extra_schemes: t.Iterable[str] | None = None,
) -> str:
    def trim_url(x: str) -> str:
        if trim_url_limit is not None and len(x) > trim_url_limit:
            return x[:trim_url_limit] + "..."
        return x

    words = re.split(r"(\s+)", str(escape(text)))

    rel_attr = f' rel="{escape(rel)}"' if rel else ""
    target_attr = f' target="{escape(target)}"' if target else ""

    for i, word in enumerate(words):
        head = ""
        middle = word
        tail = ""

        m = re.match(r"^([(<]|&lt;)+", middle)
        if m is not None:
            head = m.group(0)
            middle = middle[len(head) :]

        if middle.endswith((")", ">", ".", ",", "\n", "&gt;")):
            m = re.search(r"([)>.,\n]|&gt;)+$", middle)
            if m is not None:
                tail = m.group(0)
                middle = middle[: -len(tail)]

        for start_char, end_char in (("(", ")"), ("<", ">"), ("&lt;", "&gt;")):
            if middle.count(start_char) <= middle.count(end_char):
                continue

            for _ in range(min(middle.count(start_char), tail.count(end_char))):
                pos = tail.find(end_char)
                if pos == -1:
                    break
                pos_end = pos + len(end_char)
                middle += tail[:pos_end]
                tail = tail[pos_end:]

        if _http_re.fullmatch(middle):
            if middle.startswith(("https://", "http://")):
                middle = (
                    f'<a href="{middle}"{rel_attr}{target_attr}>{trim_url(middle)}</a>'
                )
            else:
                middle = (
                    f'<a href="https://{middle}"{rel_attr}{target_attr}>{trim_url(middle)}</a>'
                )
        elif middle.startswith("mailto:") and _email_re.match(middle[7:]):
            middle = f'<a href="{middle}">{middle[7:]}</a>'
        elif (
            "@" in middle
            and not middle.startswith("www.")
            and not middle.startswith("@")
            and ":" not in middle
            and _email_re.match(middle)
        ):
            middle = f'<a href="mailto:{middle}">{middle}</a>'
        elif extra_schemes is not None:
            for scheme in extra_schemes:
                if middle != scheme and middle.startswith(scheme):
                    middle = f'<a href="{middle}"{rel_attr}{target_attr}>{middle}</a>'
                    break

        words[i] = head + middle + tail

    return "".join(words)


def generate_lorem_ipsum(
    n: int = 5, html: bool = True, min: int = 20, max: int = 100
) -> Markup | str:
    from jinja2.constants import LOREM_IPSUM_WORDS

    if n <= 0:
        if html:
            return Markup("")
        return ""

    words = LOREM_IPSUM_WORDS.split()
    result: list[str] = []

    for _ in range(n):
        next_capitalized = True
        last_comma = 0
        last_fullstop = 0
        last: str | None = None
        p: list[str] = []

        count = random.randrange(min, max)

        for idx in range(count):
            word = random.choice(words)

            while word == last:
                word = random.choice(words)

            last = word

            if next_capitalized:
                word = word.capitalize()
                next_capitalized = False

            if idx - random.randrange(3, 8) > last_comma:
                last_comma = idx
                last_fullstop += 2
                word += ","

            if idx - random.randrange(10, 20) > last_fullstop:
                last_comma = idx
                last_fullstop = idx
                word += "."
                next_capitalized = True

            p.append(word)

        p_str = " ".join(p)

        if p_str.endswith(","):
            p_str = p_str[:-1] + "."
        elif not p_str.endswith("."):
            p_str += "."

        result.append(p_str)

    if not html:
        return "\n\n".join(result)

    return Markup("\n".join(f"<p>{escape(x)}</p>" for x in result))


def url_quote(obj: t.Any, charset: str = "utf-8", for_qs: bool = False) -> str:
    if not isinstance(obj, (bytes,)):
        if not isinstance(obj, str):
            obj = str(obj)
        obj = obj.encode(charset)

    safe = b"" if for_qs else b"/"
    rv = quote_from_bytes(t.cast(bytes, obj), safe)
    if for_qs:
        rv = rv.replace("%20", "+")
    return rv


@collections.abc.MutableMapping.register
class LRUCache:
    __copy__ = copy  # type: ignore[name-defined]

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._mapping: dict[t.Any, t.Any] = {}
        self._queue: deque[t.Any] = deque()
        self._postinit()

    def _postinit(self) -> None:
        self._popleft = self._queue.popleft
        self._pop = self._queue.pop
        self._remove = self._queue.remove
        self._append = self._queue.append
        self._wlock = Lock()

    def __getstate__(self) -> t.Mapping[str, t.Any]:
        return {"capacity": self.capacity, "_mapping": self._mapping, "_queue": self._queue}

    def __setstate__(self, d: t.Mapping[str, t.Any]) -> None:
        self.__dict__.update(d)
        self._postinit()

    def __getnewargs__(self) -> tuple[t.Any, ...]:
        return (self.capacity,)

    def __getitem__(self, key: t.Any) -> t.Any:
        with self._wlock:
            rv = self._mapping[key]
            if self._queue and self._queue[-1] != key:
                try:
                    self._remove(key)
                except ValueError:
                    pass
                self._append(key)
            return rv

    def __setitem__(self, key: t.Any, value: t.Any) -> None:
        with self._wlock:
            if key in self._mapping:
                self._remove(key)
            elif len(self._mapping) == self.capacity:
                old = self._popleft()
                del self._mapping[old]

            self._append(key)
            self._mapping[key] = value

    def __delitem__(self, key: t.Any) -> None:
        with self._wlock:
            del self._mapping[key]
            try:
                self._remove(key)
            except ValueError:
                pass

    def __contains__(self, key: t.Any) -> bool:
        return key in self._mapping

    def __len__(self) -> int:
        return len(self._mapping)

    def clear(self) -> None:
        with self._wlock:
            self._mapping.clear()
            self._queue.clear()

    def copy(self) -> te.Self:
        rv = self.__class__(self.capacity)
        rv._mapping.update(self._mapping)
        rv._queue.extend(self._queue)
        return rv

    def get(self, key: t.Any, default: t.Any = None) -> t.Any:
        try:
            return self[key]
        except KeyError:
            return default

    def setdefault(self, key: t.Any, default: t.Any = None) -> t.Any:
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default

    def __iter__(self) -> t.Iterator[t.Any]:
        return reversed(tuple(self._queue))

    def __reversed__(self) -> t.Iterator[t.Any]:
        return iter(tuple(self._queue))

    def keys(self) -> t.Iterable[t.Any]:
        return list(self)

    def items(self) -> t.Iterable[tuple[t.Any, t.Any]]:
        keys = list(self._queue)
        rv = [(k, self._mapping[k]) for k in keys]
        rv.reverse()
        return rv

    def values(self) -> t.Iterable[t.Any]:
        return [v for _, v in self.items()]

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._mapping!r}>"


def select_autoescape(
    enabled_extensions: t.Collection[str] = ("html", "htm", "xml"),
    disabled_extensions: t.Collection[str] = (),
    default_for_string: bool = True,
    default: bool = False,
) -> t.Callable[[str | None], bool]:
    enabled_patterns = tuple(f".{x.lstrip('.').lower()}" for x in enabled_extensions)
    disabled_patterns = tuple(f".{x.lstrip('.').lower()}" for x in disabled_extensions)

    def autoescape(template_name: str | None) -> bool:
        if template_name is None:
            return default_for_string

        template_name = template_name.lower()

        if template_name.endswith(enabled_patterns):
            return True

        if template_name.endswith(disabled_patterns):
            return False

        return default

    return autoescape


def autoescape(value: t.Any) -> Markup:
    return Markup.escape(value)


def htmlsafe_json_dumps(
    obj: t.Any, dumps: t.Callable[..., str] | None = None, **kwargs: t.Any
) -> Markup:
    if dumps is None:
        dumps = json.dumps

    rv = dumps(obj, **kwargs)
    rv = rv.replace("<", "\\u003c")
    rv = rv.replace(">", "\\u003e")
    rv = rv.replace("&", "\\u0026")
    rv = rv.replace("'", "\\u0027")
    return Markup(rv)


class Cycler:
    __next__ = next  # type: ignore[name-defined]

    def __init__(self, *items: t.Any) -> None:
        if len(items) == 0:
            raise RuntimeError("at least one item has to be provided")

        self.items = items
        self.pos = 0

    def reset(self) -> None:
        self.pos = 0

    @property
    def current(self) -> t.Any:
        return self.items[self.pos]

    def next(self) -> t.Any:
        rv = self.items[self.pos]
        self.pos = (self.pos + 1) % len(self.items)
        return rv


class Joiner:
    def __init__(self, sep: str = ", ") -> None:
        self.sep = sep
        self.used = False

    def __call__(self) -> str:
        if not self.used:
            self.used = True
            return ""
        return self.sep


class Namespace:
    def __init__(*args: t.Any, **kwargs: t.Any) -> None:
        self = args[0]
        args = args[1:]
        self.__attrs = dict(*args, **kwargs)

    def __getattribute__(self, name: str) -> t.Any:
        if name in {"_Namespace__attrs", "__class__"}:
            return object.__getattribute__(self, name)

        try:
            return object.__getattribute__(self, "_Namespace__attrs")[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setitem__(self, name: str, value: t.Any) -> None:
        self.__attrs[name] = value

    def __repr__(self) -> str:
        return f"<Namespace {self.__attrs!r}>"
