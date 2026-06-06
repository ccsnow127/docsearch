# jinja Baseline Documentation

## Module: utils

**purpose** The module provides core runtime utilities used across Jinja: decorators that control what implicit rendering state is passed to callables, small helpers for importing, caching, escaping, and formatting, and template-facing helper objects (cycler/joiner/namespace). It also defines a few shared singletons and registries used by the runtime, such as **missing** (a sentinel) and **internal_code** (a set of code objects marked as internal).

**classes**
- **_MissingType**: Implements the **missing** singleton sentinel used to represent “value not provided”, with stable `__repr__` / pickling behavior via `__reduce__`.
- **_PassArg**: An `enum.Enum` that encodes which implicit argument (context, eval context, or environment) should be injected when a callable is invoked during rendering; `from_obj` reads the marker set by the decorator helpers.
- **LRUCache**: A thread-safe `collections.abc.MutableMapping` implementing a small-capacity least-recently-used cache using a dict plus a deque, supporting pickling (`__getstate__` / `__setstate__`) and typical mapping operations while updating recency on access.
- **Cycler**: Template helper that cycles through provided items across calls (`current`, `next`, `reset`), enabling alternating values outside or across loops.
- **Joiner**: Template helper callable that returns `""` the first time and a separator thereafter, simplifying delimiter insertion in generated output.
- **Namespace**: A lightweight attribute container backed by an internal dict, allowing templates/extensions to store arbitrary named values with attribute-style access and item assignment.

**functions and relationships**
- **pass_context**, **pass_eval_context**, **pass_environment**: Decorators that set `f.jinja_pass_arg` to a corresponding **_PassArg** value, which the runtime can later inspect (via **_PassArg.from_obj**) to decide what to pass as the first argument when calling the function/filter/test.
- **internalcode**: Marks a function’s `__code__` object as internal by adding it to **internal_code**, used to distinguish internal frames/objects from user code.
- **is_undefined**: Checks whether a value is an instance of `jinja2.runtime.Undefined`, for filters/tests that need to treat undefined values specially.
- **consume**, **open_if_exists**, **import_string**, **object_type_repr**, **pformat**: General utilities for exhausting iterables, conditionally opening files, importing objects by string path, producing readable type descriptions, and pretty-formatting values.
- **clear_caches**: Clears Jinja’s internal environment and lexer caches by calling `environment.get_spontaneous_environment.cache_clear()` and clearing `lexer._lexer_cache`.
- **urlize**, **url_quote**, **generate_lorem_ipsum**, **select_autoescape**, **htmlsafe_json_dumps**: Template-oriented helpers for linkifying text safely (using `markupsafe.escape`), quoting URL components, generating placeholder text, choosing initial autoescape behavior based on template name/extension, and producing HTML-safe JSON (returning `markupsafe.Markup`).

---

## Class: _MissingType

**Interface:**
```python
class _MissingType:

    def __repr__(self) -> str
    def __reduce__(self) -> str
```

### Method: _MissingType.__repr__

**__repr__**: Returns the canonical string representation for the missing sentinel.
**Signature**: def __repr__(self) -> str
**Parameters**:
- self (_MissingType): the instance.
**Behavior**:
- Always returns the literal string `"missing"`.
- Does not inspect instance state and has no side effects.
**Returns**:
- str: always `"missing"`.

### Method: _MissingType.__reduce__

**__reduce__**: Provides a reduction value for pickling the missing sentinel.
**Signature**: def __reduce__(self) -> str
**Parameters**:
- self (_MissingType): the instance.
**Behavior**:
- Always returns the literal string `"missing"`.
- Does not inspect instance state and has no side effects.
**Returns**:
- str: always `"missing"`.

---

## Class: _PassArg

**Interface:**
```python
class _PassArg(enum.Enum):

    context = enum.auto()
    eval_context = enum.auto()
    environment = enum.auto()

    def from_obj(cls, obj: F) -> t.Optional['_PassArg']
```

### Method: _PassArg.from_obj

**from_obj**: Reads the `jinja_pass_arg` marker from a callable-like object and returns the corresponding `_PassArg` value if present.
**Signature**: def from_obj(cls, obj: F) -> t.Optional['_PassArg']
**Parameters**:
- cls (type[_PassArg]): the enum class (provided automatically when called as a classmethod).
- obj (F): object to inspect for a `jinja_pass_arg` attribute.
**Behavior**:
- Checks whether `obj` has an attribute named `jinja_pass_arg` using `hasattr`.
- If the attribute exists, returns `obj.jinja_pass_arg` as-is.
- If the attribute does not exist, returns `None`.
- Does not validate that the attribute value is actually an instance of `_PassArg`.
**Returns**:
- _PassArg | None: the value of `obj.jinja_pass_arg` if present, otherwise `None`.
**Notes**:
- Because `hasattr` is used, any exception raised while evaluating the attribute (other than `AttributeError`) will propagate according to Python’s `hasattr` behavior (it suppresses only `AttributeError`).

---

## Class: LRUCache

**Interface:**
```python
class LRUCache:

    __copy__ = copy

    def __init__(self, capacity: int) -> None

    def _postinit(self) -> None
    def __getstate__(self) -> t.Mapping[str, t.Any]
    def __setstate__(self, d: t.Mapping[str, t.Any]) -> None
    def __getnewargs__(self) -> tuple[t.Any, ...]
    def copy(self) -> 'te.Self'
    def get(self, key: t.Any, default: t.Any=None) -> t.Any
    def setdefault(self, key: t.Any, default: t.Any=None) -> t.Any
    def clear(self) -> None
    def __contains__(self, key: t.Any) -> bool
    def __len__(self) -> int
    def __repr__(self) -> str
    def __getitem__(self, key: t.Any) -> t.Any
    def __setitem__(self, key: t.Any, value: t.Any) -> None
    def __delitem__(self, key: t.Any) -> None
    def items(self) -> t.Iterable[tuple[t.Any, t.Any]]
    def values(self) -> t.Iterable[t.Any]
    def keys(self) -> t.Iterable[t.Any]
    def __iter__(self) -> t.Iterator[t.Any]
    def __reversed__(self) -> t.Iterator[t.Any]
```

### Method: LRUCache.__init__

**LRUCache.__init__**: Initialize an LRU (least-recently-used) cache with a fixed maximum number of entries.
**Signature**: def __init__(self, capacity: int) -> None
**Parameters**:
- self (LRUCache): The cache instance being initialized.
- capacity (int): Maximum number of key/value pairs the cache may hold; when inserting into a full cache, the least-recently-used key is evicted.
**Behavior**:
- Store the given `capacity` on the instance as `self.capacity`.
- Create an empty dictionary `self._mapping` to store key -> value.
- Create an empty `collections.deque` `self._queue` to track usage order of keys.
- Call `self._postinit()` to set up internal aliases and the write lock.
**Notes**:
- No validation of `capacity` is performed here; behavior for non-positive capacities follows from later operations (e.g., insert logic elsewhere may fail if capacity is 0).

### Method: LRUCache._postinit

**LRUCache._postinit**: Set up internal method aliases and synchronization primitives used by the cache.
**Signature**: def _postinit(self) -> None
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Create fast attribute aliases to underlying deque methods on `self._queue`:
- `self._popleft` references `self._queue.popleft`.
- `self._pop` references `self._queue.pop`.
- `self._remove` references `self._queue.remove`.
- `self._append` references `self._queue.append`.
- Create a new `threading.Lock` and store it as `self._wlock`.
**Notes**:
- This is called during normal initialization and after unpickling/restoring state to ensure the lock and method aliases exist even if only raw state was restored.

### Method: LRUCache.__getstate__

**LRUCache.__getstate__**: Provide a serializable representation of the cache state for pickling.
**Signature**: def __getstate__(self) -> t.Mapping[str, t.Any]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Return a new mapping (a `dict`) containing exactly these keys:
- `'capacity'`: the current `self.capacity`.
- `'_mapping'`: the current `self._mapping` dictionary object.
- `'_queue'`: the current `self._queue` deque object.
- Does not include transient attributes such as the lock or deque method aliases.
**Returns**:
- t.Mapping[str, t.Any]: A dict with the three entries described above.

### Method: LRUCache.__setstate__

**LRUCache.__setstate__**: Restore cache state from a mapping (typically produced by `__getstate__`) and reinitialize transient internals.
**Signature**: def __setstate__(self, d: t.Mapping[str, t.Any]) -> None
**Parameters**:
- self (LRUCache): The cache instance being restored.
- d (t.Mapping[str, t.Any]): State mapping containing at least `capacity`, `_mapping`, and `_queue` entries.
**Behavior**:
- Update the instance dictionary with all key/value pairs from `d` (equivalent to `self.__dict__.update(d)`).
- Call `self._postinit()` to recreate the lock and deque method aliases.
**Notes**:
- Any existing transient attributes (lock/aliases) are replaced by `_postinit()` after the raw state is applied.

### Method: LRUCache.__getnewargs__

**LRUCache.__getnewargs__**: Provide constructor arguments used when creating a new instance during unpickling.
**Signature**: def __getnewargs__(self) -> tuple[t.Any, ...]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Return a 1-tuple containing only the cache capacity.
**Returns**:
- tuple[t.Any, ...]: `(self.capacity,)`.

### Method: LRUCache.copy

**LRUCache.copy**: Create a shallow copy of the cache, preserving current contents and usage order.
**Signature**: def copy(self) -> 'te.Self'
**Parameters**:
- self (LRUCache): The cache instance to copy.
**Behavior**:
- Create a new instance `rv` of the same class as `self` by calling `self.__class__(self.capacity)`.
- Shallow-copy the mapping contents by updating `rv._mapping` with `self._mapping` (keys and values are not deep-copied).
- Copy the usage queue order by extending `rv._queue` with the items from `self._queue`, preserving the same left-to-right order.
- Return the new instance.
**Returns**:
- te.Self: A new cache instance with the same capacity, key/value pairs, and internal usage queue order.
**Notes**:
- The returned cache has its own lock and deque objects (created by its constructor), but contains the same key/value object references as the original (shallow copy).

### Method: LRUCache.get

**LRUCache.get**: Retrieve a value by key, returning a default if the key is not present, and updating LRU order on hits.
**Signature**: def get(self, key: t.Any, default: t.Any=None) -> t.Any
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): Key to look up.
- default (t.Any): Value to return if `key` is not present; defaults to `None`.
**Behavior**:
- Attempt to return `self[key]` (i.e., delegate to `__getitem__`).
- On a hit, this has the side effect of updating the internal LRU order as implemented by `__getitem__`.
- If `__getitem__` raises `KeyError`, return `default` instead.
**Returns**:
- t.Any: The cached value if present; otherwise `default`.

### Method: LRUCache.setdefault

**LRUCache.setdefault**: Return the existing value for a key if present (updating LRU order), otherwise insert and return a default value.
**Signature**: def setdefault(self, key: t.Any, default: t.Any=None) -> t.Any
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): Key to look up or insert.
- default (t.Any): Value to store and return if `key` is missing; defaults to `None`.
**Behavior**:
- Attempt to return `self[key]` (delegates to `__getitem__`).
- If present, the access updates LRU order per `__getitem__`.
- If a `KeyError` is raised (key missing):
- Assign `default` into the cache via `self[key] = default` (delegates to `__setitem__`, which may evict an old entry if at capacity and will update LRU order).
- Return `default`.
**Returns**:
- t.Any: The existing cached value if present; otherwise the `default` value after inserting it.

### Method: LRUCache.clear

**LRUCache.clear**: Remove all entries from the cache.
**Signature**: def clear(self) -> None
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Acquire the instance write lock `self._wlock` using a context manager.
- Clear the internal mapping dictionary (`self._mapping.clear()`), removing all key/value pairs.
- Clear the internal usage queue deque (`self._queue.clear()`), removing all tracked keys.
- Release the lock when leaving the context manager.
**Notes**:
- This method is thread-synchronized using the cache’s lock.

### Method: LRUCache.__contains__

**LRUCache.__contains__**: Test whether a key is currently stored in the cache.
**Signature**: def __contains__(self, key: t.Any) -> bool
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): Key to test for membership.
**Behavior**:
- Return the result of `key in self._mapping`.
- Does not acquire the lock and does not update LRU order.
**Returns**:
- bool: `True` if `key` is present in the internal mapping, otherwise `False`.
**Notes**:
- Because it checks only `_mapping`, it reflects whether the key is stored, regardless of whether `_queue` might be temporarily inconsistent.

### Method: LRUCache.__len__

**LRUCache.__len__**: Return the number of key/value pairs currently stored in the cache.
**Signature**: def __len__(self) -> int
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Compute the size by taking the length of the internal mapping that stores cached key/value pairs.
- Do not modify cache ordering or contents.
- Do not acquire the cache lock; it directly reads the mapping length.
**Returns**:
- int: The current number of entries in the cache.

### Method: LRUCache.__repr__

**LRUCache.__repr__**: Return a developer-facing string representation showing the cache type and its internal mapping.
**Signature**: def __repr__(self) -> str
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Build and return a string in the form `<{ClassName} {mapping_repr}>`.
- `{ClassName}` is the runtime class name (`type(self).__name__`).
- `{mapping_repr}` is the `repr` of the internal mapping (`self._mapping!r`).
- Does not acquire the cache lock and does not modify cache state.
**Returns**:
- str: The formatted representation string.

### Method: LRUCache.__getitem__

**LRUCache.__getitem__**: Retrieve a value by key and mark that key as most-recently-used.
**Signature**: def __getitem__(self, key: t.Any) -> t.Any
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): The lookup key.
**Behavior**:
- Acquire the instance write lock (`self._wlock`) for the duration of the operation.
- Look up the value in the internal mapping using `self._mapping[key]`.
- If the key is not present, allow the mapping access to raise `KeyError` (propagate it).
- If the key is not already the most-recently-used key (i.e. the last element of the internal queue is not equal to `key`):
- Attempt to remove `key` from the internal queue.
- If removal raises `ValueError` (key not found in the queue), ignore the error.
- Append `key` to the right end of the queue to mark it as most-recently-used.
- Return the retrieved value.
**Returns**:
- t.Any: The value associated with `key`.
**Notes**:
- The queue tracks usage order; the right end is most-recently-used.
- The `ValueError` suppression ensures robustness if the queue and mapping become temporarily inconsistent.

### Method: LRUCache.__setitem__

**LRUCache.__setitem__**: Store a key/value pair and mark the key as most-recently-used, evicting the least-recently-used entry if at capacity.
**Signature**: def __setitem__(self, key: t.Any, value: t.Any) -> None
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): The key to insert or update.
- value (t.Any): The value to associate with `key`.
**Behavior**:
- Acquire the instance write lock (`self._wlock`) for the duration of the operation.
- If `key` already exists in the internal mapping:
- Remove `key` from the internal queue (so it can be re-appended as most-recently-used).
- Else (key does not exist):
- If the cache is at capacity (i.e. `len(self._mapping) == self.capacity`):
- Pop the least-recently-used key from the left end of the queue.
- Delete that key from the internal mapping.
- Append `key` to the right end of the queue (most-recently-used position).
- Set `self._mapping[key] = value` (insert or overwrite).
- No value is returned.
**Notes**:
- Eviction removes exactly one entry when at capacity and inserting a new key.
- If `capacity` is 0, the condition `len(self._mapping) == self.capacity` will be true initially and the method will attempt to pop from an empty queue, causing an exception from the deque operation.

### Method: LRUCache.__delitem__

**LRUCache.__delitem__**: Delete a key/value pair from the cache and remove its key from the usage queue.
**Signature**: def __delitem__(self, key: t.Any) -> None
**Parameters**:
- self (LRUCache): The cache instance.
- key (t.Any): The key to delete.
**Behavior**:
- Acquire the instance write lock (`self._wlock`) for the duration of the operation.
- Delete the key from the internal mapping using `del self._mapping[key]`.
- If the key is not present, propagate the resulting `KeyError`.
- Attempt to remove the key from the internal queue.
- If removal raises `ValueError` (key not found in the queue), ignore the error.
- No value is returned.
**Notes**:
- The `ValueError` suppression ensures deletion succeeds even if the queue does not contain the key.

### Method: LRUCache.items

**LRUCache.items**: Return key/value pairs ordered from most-recently-used to least-recently-used.
**Signature**: def items(self) -> t.Iterable[tuple[t.Any, t.Any]]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Create a snapshot list of keys from the internal queue by first converting the queue to a list (`list(self._queue)`).
- Build a list of `(key, value)` pairs by iterating over that snapshot list in its original order (oldest to newest) and looking up each value in the internal mapping (`self._mapping[key]`).
- Reverse the resulting list in place so that the final order is newest to oldest (most-recently-used first).
- Return the reversed list.
- Does not acquire the cache lock.
**Returns**:
- t.Iterable[tuple[t.Any, t.Any]]: A concrete list of `(key, value)` tuples ordered by most-recently-used first.
**Notes**:
- Because it snapshots keys but looks up values afterward, concurrent mutation could raise `KeyError` if a key from the snapshot is missing from the mapping at lookup time.

### Method: LRUCache.values

**LRUCache.values**: Return values ordered by most-recently-used to least-recently-used.
**Signature**: def values(self) -> t.Iterable[t.Any]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Call `self.items()` to obtain `(key, value)` pairs ordered most-recently-used first.
- Construct and return a new list containing only the second element (value) from each pair, preserving that order.
- Does not acquire the cache lock beyond whatever `items()` does (it does not lock either).
**Returns**:
- t.Iterable[t.Any]: A concrete list of values ordered by most-recently-used first.

### Method: LRUCache.keys

**LRUCache.keys**: Return keys ordered by most-recently-used to least-recently-used.
**Signature**: def keys(self) -> t.Iterable[t.Any]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Return `list(self)`, relying on `__iter__` to iterate keys from most-recently-used to least-recently-used.
- Produces a concrete list.
- Does not acquire the cache lock.
**Returns**:
- t.Iterable[t.Any]: A concrete list of keys ordered by most-recently-used first.

### Method: LRUCache.__iter__

**LRUCache.__iter__**: Iterate over keys from most-recently-used to least-recently-used.
**Signature**: def __iter__(self) -> t.Iterator[t.Any]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Create an immutable snapshot of the internal queue by converting it to a tuple (`tuple(self._queue)`).
- Return an iterator that yields that tuple in reverse order (`reversed(...)`).
- Since the queue stores oldest-to-newest, reversing yields newest-to-oldest.
- Does not acquire the cache lock.
**Returns**:
- t.Iterator[t.Any]: An iterator over keys, most-recently-used first.

### Method: LRUCache.__reversed__

**LRUCache.__reversed__**: Iterate over keys from least-recently-used to most-recently-used.
**Signature**: def __reversed__(self) -> t.Iterator[t.Any]
**Parameters**:
- self (LRUCache): The cache instance.
**Behavior**:
- Create an immutable snapshot of the internal queue by converting it to a tuple (`tuple(self._queue)`).
- Return an iterator over that tuple in its natural order (`iter(...)`).
- Since the queue stores oldest-to-newest, this yields least-recently-used first.
- Does not acquire the cache lock.
**Returns**:
- t.Iterator[t.Any]: An iterator over keys, least-recently-used first.

---

## Class: Cycler

**Interface:**
```python
class Cycler:

    __next__ = next

    def __init__(self, *items: t.Any) -> None

    def reset(self) -> None
    def current(self) -> t.Any
    def next(self) -> t.Any
```

### Method: Cycler.__init__

**Cycler.__init__**: Initialize a Cycler with one or more items and set the starting position to the first item.
**Signature**: def __init__(self, *items: t.Any) -> None
**Parameters**:
- items (t.Any): One or more positional values to cycle through in the given order; must not be empty.
**Behavior**:
- If no items are provided (len(items) == 0), raise RuntimeError with the message "at least one item has to be provided".
- Otherwise:
- Assign self.items = items (the received positional arguments tuple).
- Assign self.pos = 0.
- No copying or transformation of items is performed.
**Notes**:
- The stored items are indexed directly; therefore they must support tuple indexing semantics via the stored tuple.

### Method: Cycler.reset

**Cycler.reset**: Reset the cycle so that the next value returned will be the first item.
**Signature**: def reset(self) -> None
**Parameters**:
- (none)
**Behavior**:
- Set self.pos to 0 unconditionally.
- Does not modify self.items.
**Notes**:
- After calling reset, current will refer to the first element of items and next() will return that first element.

### Method: Cycler.current

**Cycler.current**: Return the current item without advancing the cycle.
**Signature**: def current(self) -> t.Any
**Parameters**:
- (none)
**Behavior**:
- Return self.items[self.pos].
- Does not change self.pos.
- This is implemented as a read-only property in the original API (accessed without parentheses).
**Returns**:
- The item at the current position index.
**Notes**:
- The value returned is exactly the object stored in items; no copying is performed.

### Method: Cycler.next

**Cycler.next**: Return the current item and advance the cycle position to the next item, wrapping to the start when reaching the end.
**Signature**: def next(self) -> t.Any
**Parameters**:
- (none)
**Behavior**:
- Read the current item (equivalent to self.items[self.pos]) and store it as the return value.
- Advance the position with wrap-around:
- Compute self.pos = (self.pos + 1) % len(self.items).
- Return the previously stored current item.
- The class also assigns __next__ = next so that iterator-style next(cycler) works.
**Returns**:
- The item that was current before advancing.
**Notes**:
- Because modulo is used, the cycle repeats indefinitely and never raises StopIteration.

---

## Class: Joiner

**Interface:**
```python
class Joiner:

    def __init__(self, sep: str=', ') -> None

    def __call__(self) -> str
```

### Method: Joiner.__init__

**Joiner.__init__**: Initialize a Joiner with a separator and mark it as unused.
**Signature**: def __init__(self, sep: str=', ') -> None
**Parameters**:
- sep (str): Separator string to return on every call after the first; defaults to ", ".
**Behavior**:
- Assign self.sep = sep.
- Assign self.used = False.
- Does not validate sep beyond storing it.
**Notes**:
- The first call to the instance will return an empty string regardless of sep; subsequent calls return sep unchanged.

### Method: Joiner.__call__

**Joiner.__call__**: Return an empty string the first time it is called, then return the configured separator on subsequent calls.
**Signature**: def __call__(self) -> str
**Parameters**:
- (none)
**Behavior**:
- Check the instance attribute `used`.
- If `used` is false:
- Set `used` to true.
- Return the empty string `""`.
- Otherwise (if `used` is true):
- Return the instance attribute `sep` unchanged.
- Side effect: mutates `self.used` from false to true on the first call.
**Returns**:
- `""` on the first call for a given instance.
- `self.sep` on every later call for that instance.
**Notes**:
- Correct behavior depends on `Joiner.__init__` having initialized `self.used` (typically to `False`) and `self.sep` (to the separator string).

---

## Class: Namespace

**Interface:**
```python
class Namespace:

    def __init__(*args: t.Any, **kwargs: t.Any) -> None

    def __getattribute__(self, name: str) -> t.Any
    def __setitem__(self, name: str, value: t.Any) -> None
    def __repr__(self) -> str
```

### Method: Namespace.__init__

**Namespace.__init__**: Initialize the namespace's internal attribute dictionary from positional and keyword arguments accepted by `dict()`.
**Signature**: def __init__(*args: t.Any, **kwargs: t.Any) -> None
**Parameters**:
- args (t.Any): The first element is the instance (`self`); remaining positional arguments are forwarded to `dict(*args, **kwargs)` to build the initial mapping.
- kwargs (t.Any): Keyword arguments forwarded to `dict(*args, **kwargs)` to build the initial mapping.
**Behavior**:
- Accept `self` via the first element of the variadic `*args` (i.e., do not declare `self` explicitly in the signature).
- Split the incoming `args` tuple into:
- `self = args[0]`
- `args = args[1:]` (the remaining positional arguments intended for `dict`).
- Create the internal storage dict by calling `dict(*args, **kwargs)`.
- This must follow Python's `dict` constructor rules (e.g., allow a mapping, an iterable of key/value pairs, etc., plus keyword overrides).
- Any `TypeError` raised by invalid `dict` construction should propagate.
- Store the resulting dict on the instance as a private attribute named `__attrs` (which becomes `_Namespace__attrs` due to name mangling).
- No other side effects.
**Notes**:
- The internal attribute must be named exactly `__attrs` in the class body so that name mangling produces `_Namespace__attrs`, which is relied upon by `__getattribute__`.

### Method: Namespace.__getattribute__

**Namespace.__getattribute__**: Resolve attribute reads from the internal namespace dictionary, with special handling for internal attributes.
**Signature**: def __getattribute__(self, name: str) -> t.Any
**Parameters**:
- name (str): The attribute name being accessed.
**Behavior**:
- If `name` is exactly `_Namespace__attrs` or `__class__`:
- Return `object.__getattribute__(self, name)` directly.
- Otherwise:
- Attempt to return `self.__attrs[name]` (i.e., look up `name` as a key in the internal dict).
- If the key is not present:
- Raise `AttributeError(name)`.
- The raised `AttributeError` must not chain the original `KeyError` (i.e., suppress context so it appears as if no `KeyError` occurred).
**Returns**:
- The value stored under key `name` in the internal dict when present.
**Notes**:
- The `__class__` bypass is required so that runtime mechanisms that inspect `__class__` (such as awaitable checks) continue to work.
- This method intentionally does not fall back to normal instance attributes for arbitrary names; only the two special names bypass the dict lookup.

### Method: Namespace.__setitem__

**Namespace.__setitem__**: Store a value in the namespace under the given name key.
**Signature**: def __setitem__(self, name: str, value: t.Any) -> None
**Parameters**:
- name (str): The key under which to store the value; also the attribute name that will be readable via `obj.<name>`.
- value (t.Any): The value to store.
**Behavior**:
- Assign `value` into the internal dict: `self.__attrs[name] = value`.
- Overwrites any existing value for the same key.
- No return value.
**Notes**:
- This is item assignment (`obj[name] = value`), not attribute assignment (`obj.name = value`). Attribute assignment is not defined here and would follow default behavior unless separately implemented.

### Method: Namespace.__repr__

**Namespace.__repr__**: Return a developer-facing representation showing the namespace contents.
**Signature**: def __repr__(self) -> str
**Parameters**:
- (none)
**Behavior**:
- Produce and return a string in the exact format: `<Namespace {attrs_repr}>`.
- `{attrs_repr}` is the result of `repr(self.__attrs)`.
- No side effects.
**Returns**:
- A `str` representation of the instance including the `repr` of its internal dict.

---

## Function: pass_context

```python
def pass_context(f: F) -> F
```

**pass_context**: Decorator that marks a callable to receive a Jinja runtime Context as its first argument when invoked during template rendering.
**Signature**: def pass_context(f: F) -> F
**Parameters**:
- f (F): a callable to mark; must be an object that allows setting arbitrary attributes.
**Behavior**:
- Sets an attribute named `jinja_pass_arg` on `f` to `_PassArg.context`.
- Returns the same callable object `f` (no wrapping is performed).
- Intended for use by Jinja’s call machinery, which checks this marker to decide what to inject.
**Returns**:
- F: the original callable `f`, after attaching the marker attribute.
**Notes**:
- If `f` does not allow attribute assignment, setting `jinja_pass_arg` will raise an exception from Python’s attribute setting semantics.

---

## Function: pass_eval_context

```python
def pass_eval_context(f: F) -> F
```

**pass_eval_context**: Decorator that marks a callable to receive a Jinja EvalContext as its first argument when invoked during template rendering.
**Signature**: def pass_eval_context(f: F) -> F
**Parameters**:
- f (F): a callable to mark; must be an object that allows setting arbitrary attributes.
**Behavior**:
- Sets an attribute named `jinja_pass_arg` on `f` to `_PassArg.eval_context`.
- Returns the same callable object `f` (no wrapping is performed).
- Intended for use by Jinja’s call machinery, which checks this marker to decide what to inject.
**Returns**:
- F: the original callable `f`, after attaching the marker attribute.
**Notes**:
- If `f` does not allow attribute assignment, setting `jinja_pass_arg` will raise an exception from Python’s attribute setting semantics.

---

## Function: pass_environment

```python
def pass_environment(f: F) -> F
```

**pass_environment**: Decorator that marks a callable (commonly a filter, test, or global callable) to receive a Jinja `Environment` instance as its first positional argument when invoked by Jinja during template rendering.

**Signature**: def pass_environment(f: F) -> F

**Parameters**:
- f (F): A callable to mark; must be an object that allows setting arbitrary attributes via normal Python attribute assignment semantics.

**Behavior**:
- **Docstring contract (non-functional requirement)**:
  - The function object `pass_environment` itself must have a non-empty `__doc__` string.
  - The docstring must contain the literal substring `"Environment"` and must also mention that the decorator is used for Jinja “filters” (the docstring must contain the literal substring `"filters"` somewhere in its text).
  - The docstring must state the key semantic: an `Environment` instance is passed as the first argument to decorated callables when they are invoked by the template engine (e.g., for filters during rendering).
  - The docstring must be safe to read in isolation:
    - Accessing `pass_environment.__doc__` must not require importing `Environment` (or any other module) at docstring access time.
    - Any mention of `Environment` must be purely textual; do not rely on docstring constructs that could trigger imports or evaluation when the docstring is accessed or inspected.
    - The docstring must remain readable even in environments where imports are monkeypatched to raise `ImportError`; reading `__doc__` must not attempt any import.
  - If `pass_environment` is re-exported or aliased from another module, it must retain this same docstring through the public import path (i.e., consumers must see the docstring that includes `"Environment"` and `"filters"` when reading `pass_environment.__doc__`).
- **Decorator behavior (functional requirement)**:
  - When called as `pass_environment(f)`, it sets an attribute named `jinja_pass_arg` on `f` to the enum value `_PassArg.environment`.
  - No wrapper function is created; `f` is returned as-is, with only the marker attribute attached/updated.
  - This marker is intended for Jinja’s internal calling machinery, which checks `jinja_pass_arg` to decide whether to inject an `Environment` instance as the first positional argument when calling `f` during template rendering (including when `f` is used as a filter).
- **Edge cases and side effects**:
  - If `f` does not allow attribute assignment (e.g., certain built-ins or extension types), attempting to set `f.jinja_pass_arg` raises the underlying Python exception (commonly `AttributeError` or `TypeError`); the exception is not caught.
  - If `f` already has a `jinja_pass_arg` attribute, it is overwritten.

**Returns**:
- F: The same callable object `f`, after attaching (or updating) the `jinja_pass_arg` marker attribute.

---

## Function: internalcode

```python
def internalcode(f: F) -> F
```

**internalcode**: Decorator that records a function’s code object in a module-level set to mark it as internally used.
**Signature**: def internalcode(f: F) -> F
**Parameters**:
- f (F): a callable with a `__code__` attribute (i.e., typically a Python function).
**Behavior**:
- Adds `f.__code__` to the module-level mutable set `internal_code`.
- Returns the same callable object `f` (no wrapping is performed).
- Side effect: mutates the shared `internal_code` set.
**Returns**:
- F: the original callable `f`.
**Notes**:
- If `f` lacks `__code__`, attribute access will raise an exception.
- Re-adding an existing code object is a no-op due to set semantics.

---

## Function: is_undefined

```python
def is_undefined(obj: t.Any) -> bool
```

**is_undefined**: Determines whether an object is a Jinja `Undefined` instance.
**Signature**: def is_undefined(obj: t.Any) -> bool
**Parameters**:
- obj (typing.Any): value to test.
**Behavior**:
- Imports `Undefined` from the module’s sibling `runtime` module at call time.
- Returns the result of `isinstance(obj, Undefined)`.
- No other checks or conversions are performed.
**Returns**:
- bool: `True` if `obj` is an instance of `jinja2.runtime.Undefined`, otherwise `False`.
**Notes**:
- The import occurs inside the function, so import-time side effects (if any) happen when the function is first called rather than at module import.

---

## Function: consume

```python
def consume(iterable: t.Iterable[t.Any]) -> None
```

**consume**: Exhaust an iterable completely without producing any output.
**Signature**: def consume(iterable: t.Iterable[t.Any]) -> None
**Parameters**:
- iterable (t.Iterable[t.Any]): Any iterable to be fully iterated; items are ignored.
**Behavior**:
- Iterate over `iterable` from start to exhaustion using a `for` loop.
- For each yielded item, do nothing (discard it).
- Stops only when the iterable is exhausted or iteration raises an exception from the iterable.
- Has no side effects other than advancing/consuming the iterable.
**Notes**:
- If `iterable` is an iterator/generator, it will be exhausted after this call.
- Any exception raised during iteration propagates to the caller.

---

## Function: clear_caches

```python
def clear_caches() -> None
```

**clear_caches**: Clear Jinja's internal caches used for spontaneous environments and lexers.
**Signature**: def clear_caches() -> None
**Parameters**:
- (none)
**Behavior**:
- Import `get_spontaneous_environment` from `jinja2.environment`.
- Import `_lexer_cache` from `jinja2.lexer`.
- Call `get_spontaneous_environment.cache_clear()` to clear the function's internal cache.
- Call `_lexer_cache.clear()` to remove all cached lexer entries.
- Performs no other work and returns.
**Notes**:
- Intended for scenarios like memory measurement; normal usage typically does not require calling this.

---

## Function: import_string

```python
def import_string(import_name: str, silent: bool=False) -> t.Any
```

**import_string**: Import and return a Python object specified by a string module path.
**Signature**: def import_string(import_name: str, silent: bool=False) -> t.Any
**Parameters**:
- import_name (str): Import path in one of these forms: `pkg.mod:obj`, `pkg.mod.obj`, or a top-level module name with no separators.
- silent (bool): If `True`, suppress `ImportError` and `AttributeError` and return `None` instead; if `False`, re-raise those errors.
**Behavior**:
- Attempt to resolve `import_name` as follows:
- If `":"` is present, split on the first colon into `module` and `obj`.
- Else if `"."` is present, split using `rpartition(".")` into `module` and `obj` (module is everything before the last dot).
- Else (no colon and no dot), import and return the module object via `__import__(import_name)`.
- If a `module` and `obj` were determined:
- Import the module using `__import__(module, None, None, [obj])` (ensures the returned object is the module, not the top-level package).
- Return `getattr(imported_module, obj)`.
- If importing the module or accessing the attribute raises `ImportError` or `AttributeError`:
- If `silent` is `False`, re-raise the exception.
- If `silent` is `True`, return `None`.
**Returns**:
- The imported module (when `import_name` has no `:` or `.`), or the imported attribute from the specified module.
- `None` only when `silent=True` and an `ImportError` or `AttributeError` occurs.
**Notes**:
- Only `ImportError` and `AttributeError` are handled; other exceptions propagate.
- For dotted paths, only the last segment is treated as the attribute name; everything before it is the module path.

---

## Function: open_if_exists

```python
def open_if_exists(filename: str, mode: str='rb') -> t.IO[t.Any] | None
```

**open_if_exists**: Open and return a file handle only if the path exists as a regular file.
**Signature**: def open_if_exists(filename: str, mode: str='rb') -> t.IO[t.Any] | None
**Parameters**:
- filename (str): Path to check and open.
- mode (str): Mode passed to `open`; defaults to binary read (`'rb'`).
**Behavior**:
- Check `os.path.isfile(filename)`.
- If the check is false, return `None` without attempting to open.
- If true, call Python built-in `open(filename, mode)` and return the resulting file object.
- Any exception from `open` (e.g., permission errors) propagates.
**Returns**:
- A file object from `open` if `filename` exists and is a file; otherwise `None`.
**Notes**:
- This does not check readability/writability beyond what `open` enforces.

---

## Function: object_type_repr

```python
def object_type_repr(obj: t.Any) -> str
```

**object_type_repr**: Produce a human-readable string describing an object's type, with special handling for certain singletons.
**Signature**: def object_type_repr(obj: t.Any) -> str
**Parameters**:
- obj (t.Any): The object to describe.
**Behavior**:
- If `obj is None`, return the literal string `"None"`.
- Else if `obj is Ellipsis`, return the literal string `"Ellipsis"`.
- Otherwise:
- Determine `cls = type(obj)`.
- If `cls.__module__ == "builtins"`, return `f"{cls.__name__} object"`.
- Else return `f"{cls.__module__}.{cls.__name__} object"`.
**Returns**:
- A string naming the singleton (`None`/`Ellipsis`) or describing the type as above.
**Notes**:
- The returned format always ends with the word `"object"` for non-singletons.

---

## Function: pformat

```python
def pformat(obj: t.Any) -> str
```

**pformat**: Pretty-format an object using Python's standard library pretty printer.
**Signature**: def pformat(obj: t.Any) -> str
**Parameters**:
- obj (t.Any): Any object to format.
**Behavior**:
- Import `pformat` from the `pprint` module at call time.
- Return `pprint.pformat(obj)`.
**Returns**:
- The pretty-printed string representation of `obj` as produced by `pprint.pformat`.
**Notes**:
- Formatting details (width, sorting, etc.) are whatever `pprint.pformat` defaults to in the running Python version.

---

## Function: urlize

```python
def urlize(text: str, trim_url_limit: int | None=None, rel: str | None=None, target: str | None=None, extra_schemes: t.Iterable[str] | None=None) -> str
```

**urlize**: Convert recognized URLs and email addresses in text into HTML anchor tags, preserving surrounding punctuation.
**Signature**: def urlize(text: str, trim_url_limit: int | None=None, rel: str | None=None, target: str | None=None, extra_schemes: t.Iterable[str] | None=None) -> str
**Parameters**:
- text (str): Input text in which to detect links; will be HTML-escaped before linkification.
- trim_url_limit (int | None): If not `None`, displayed link text for HTTP/HTTPS/www links is truncated to at most this many characters, appending `...` when truncated.
- rel (str | None): If provided, add `rel="..."` attribute to generated non-mailto links (HTTP/HTTPS/www and extra schemes); value is HTML-escaped.
- target (str | None): If provided, add `target="..."` attribute to generated non-mailto links (HTTP/HTTPS/www and extra schemes); value is HTML-escaped.
- extra_schemes (t.Iterable[str] | None): If provided, additionally recognize tokens that start with any given scheme string and wrap them in a link.
**Behavior**:
- Define an internal `trim_url(x)` function:
- If `trim_url_limit` is not `None` and `len(x) > trim_url_limit`, return `x[:trim_url_limit] + "..."`; otherwise return `x` unchanged.
- If `trim_url_limit` is `None`, always return `x` unchanged.
- Escape the entire input text for HTML using `markupsafe.escape(text)`, convert to `str`, then split into a list using `re.split(r"(\s+)", ...)` so that whitespace separators are preserved as separate list elements.
- Precompute attribute snippets:
- `rel_attr` is `" rel=\"<escaped rel>\""` if `rel` is truthy, else empty string.
- `target_attr` is `" target=\"<escaped target>\""` if `target` is truthy, else empty string.
- For each element `word` in the split list (including whitespace elements):
- Initialize `head=""`, `middle=word`, `tail=""`.
- Detect and strip leading punctuation from `middle`:
- If `re.match(r"^([(<]|&lt;)+", middle)` matches, set `head` to the matched prefix and remove it from the start of `middle`.
- Detect and strip trailing punctuation from `middle`:
- Only attempt if `middle` ends with one of `")", ">", ".", ",", "\n", "&gt;"`.
- If so, `re.search(r"([)>.,\n]|&gt;)+$", middle)`; if it matches, set `tail` to the matched suffix and remove it from the end of `middle`.
- Attempt to rebalance delimiters by moving closing delimiters from `tail` back into `middle` when `middle` contains more opening than closing delimiters:
- For each pair `(start_char, end_char)` in `("(", ")")`, `("<", ">")`, `("&lt;", "&gt;")`:
- Count occurrences in `middle`. If `middle.count(start_char) <= middle.count(end_char)`, do nothing.
- Otherwise, move up to `min(middle.count(start_char), tail.count(end_char))` occurrences from the start of `tail` into the end of `middle`:
- Repeatedly find the first occurrence of `end_char` in `tail`, take everything up to and including it, append that substring to `middle`, and remove it from the start of `tail`.
- Linkification checks are applied to `middle` in this order (first match wins):
- If `_http_re` fully matches `middle`:
- If `middle` starts with `"https://"` or `"http://"`, replace `middle` with an `<a>` tag whose `href` is exactly `middle`, includes `rel_attr` and `target_attr`, and whose link text is `trim_url(middle)`.
- Otherwise (e.g., starts with `www.` or a bare domain matched by the regex), replace `middle` with an `<a>` tag whose `href` is `"https://" + middle`, includes `rel_attr` and `target_attr`, and whose link text is `trim_url(middle)`.
- Else if `middle` starts with `"mailto:"` and `_email_re` matches `middle[7:]`:
- Replace `middle` with `<a href="{middle}">{middle[7:]}</a>` (no `rel`/`target` attributes).
- Else if all of the following are true:
- `"@" in middle`
- `not middle.startswith("www.")`
- `not middle.startswith("@")`
- `":" not in middle`
- `_email_re` matches `middle`
- Then replace `middle` with `<a href="mailto:{middle}">{middle}</a>`.
- Else if `extra_schemes is not None`:
- For each `scheme` in `extra_schemes`, if `middle != scheme` and `middle.startswith(scheme)`, replace `middle` with `<a href="{middle}"{rel_attr}{target_attr}>{middle}</a>`.
- Replace the list element with the concatenation `head + middle + tail`.
- Join all list elements with `"".join(words)` and return the resulting string.
**Returns**:
- A string containing HTML-escaped original text with recognized links replaced by `<a>` tags.
**Notes**:
- Because the input is escaped before processing, any `<` and `>` in the original text appear as `&lt;` and `&gt;` during parsing, and the function explicitly treats those as possible surrounding punctuation.
- Only the displayed text for HTTP/HTTPS/www links is trimmed; the `href` remains untrimmed.
- `rel` and `target` are not applied to `mailto:` links created by the email branches.
- Whitespace tokens are preserved exactly as split by the regex, including newlines when they are part of whitespace runs.

---

## Function: generate_lorem_ipsum

```python
def generate_lorem_ipsum(n: int=5, html: bool=True, min: int=20, max: int=100) -> str
```

**generate_lorem_ipsum**: Generate pseudo-random “lorem ipsum” filler text as either plain-text paragraphs or HTML `<p>` paragraphs; when HTML is requested the output is marked safe.

**Signature**: def generate_lorem_ipsum(n: int = 5, html: bool = True, min: int = 20, max: int = 100) -> "markupsafe.Markup | str"

**Parameters**:
- n (int): Number of paragraphs to generate. If `n <= 0`, no paragraphs are generated and the function returns an empty string of the appropriate type (empty `str` when `html=False`, empty `markupsafe.Markup` when `html=True`).
- html (bool): If `True`, return HTML paragraphs as a `markupsafe.Markup` instance (safe HTML). If `False`, return plain text as a built-in `str`.
- min (int): Lower bound passed to `random.randrange(min, max)` for the number of words per paragraph. This is the `start` argument to `randrange` (inclusive). Must be valid for `randrange`; if invalid (for example `min >= max`), `random.randrange` raises `ValueError` and it propagates unchanged.
- max (int): Upper bound passed to `random.randrange(min, max)` for the number of words per paragraph. This is the `stop` argument to `randrange` (exclusive). Must be valid for `randrange`; if invalid (for example `min >= max`), `random.randrange` raises `ValueError` and it propagates unchanged.

**Behavior**:
- Knowledge-gap clarification (how to stay correct despite missing failing tests):
  - The function’s output is intentionally non-deterministic unless the caller seeds Python’s global `random` generator; therefore, correctness must be judged by invariants (types, separators, HTML escaping/safety, paragraph count, and punctuation termination) rather than exact word sequences or exact punctuation frequency.
  - No additional hidden normalization (such as trimming trailing whitespace beyond what joining produces) is performed; the only enforced formatting invariant is that each paragraph ends with a period.
- Dependencies and randomness:
  - Import `LOREM_IPSUM_WORDS` from `jinja2.constants`.
  - Split `LOREM_IPSUM_WORDS` on whitespace to obtain the candidate word list `words`.
  - Use the standard library `random` module functions `choice` and `randrange` for pseudo-random selection.
  - No seeding is performed inside the function; callers may seed `random` externally to obtain deterministic output.
  - Only side effect is consumption of randomness from the global `random` generator.
- Overall structure:
  - Initialize an empty list `result` to collect generated paragraph strings (each paragraph is a single `str`).
  - If `n > 0`, iterate exactly `n` times (paragraph indices `0` through `n - 1`) and generate one paragraph per iteration.
  - If `n <= 0`, skip paragraph generation entirely and return empty output of the appropriate type immediately.
- Per-paragraph generation:
  - Initialize state for the paragraph:
    - `next_capitalized = True` (the next selected word should be capitalized).
    - `last_comma = 0` and `last_fullstop = 0` (track indices where punctuation was last inserted).
    - `last = None` (track the last chosen word to avoid immediate repetition).
    - `p = []` (list of word tokens for this paragraph; each token may include trailing punctuation).
  - Determine the number of word tokens to generate as `count = random.randrange(min, max)` and iterate `idx` from `0` to `count - 1`.
  - Word selection and immediate-repeat avoidance:
    - Select `word = random.choice(words)` repeatedly until `word != last` (prevents the same word appearing twice consecutively within the same paragraph).
    - Set `last = word`.
  - Capitalization rule:
    - If `next_capitalized` is `True`, replace `word` with `word.capitalize()` and set `next_capitalized = False`.
    - Capitalization is applied before punctuation is appended for that token.
  - Punctuation insertion (performed on the current token before appending to `p`):
    - Comma insertion rule (evaluated before full stop insertion for the same token):
      - Compute a spacing threshold using `random.randrange(3, 8)`.
      - If `idx - random.randrange(3, 8) > last_comma`, then:
        - Set `last_comma = idx`.
        - Increment `last_fullstop` by `2`.
        - Append `","` to the current token (token becomes `word + ","`).
    - Full stop insertion rule:
      - Compute a spacing threshold using `random.randrange(10, 20)`.
      - If `idx - random.randrange(10, 20) > last_fullstop`, then:
        - Set `last_comma = idx` and `last_fullstop = idx`.
        - Append `"."` to the current token (token becomes `word + "."` or `word + ",."` if a comma was appended earlier in the same step).
        - Set `next_capitalized = True` so the next word begins a new sentence and is capitalized.
  - Append the resulting token to `p`.
  - Convert tokens to paragraph text:
    - Join tokens in `p` with single spaces to form `p_str = " ".join(p)`.
  - Paragraph termination invariant (observable output rule):
    - Ensure the final paragraph string ends with a period:
      - If `p_str` ends with a comma, replace the final comma with a period.
      - Else if `p_str` does not end with a period, append a period.
    - This enforcement happens regardless of punctuation inserted during token generation.
  - Append `p_str` to `result`.
- Final formatting and return:
  - If `html` is `False`:
    - Return `"\n\n".join(result)` (paragraphs separated by exactly one blank line).
    - Return type is a built-in `str` (not `Markup`), even if the content happens to look like HTML.
    - If `n <= 0`, the returned value is exactly `""`.
  - If `html` is `True`:
    - Escape each paragraph string with `markupsafe.escape` before embedding in HTML (ensures any special characters in the generated text are HTML-escaped).
    - Wrap each escaped paragraph in `<p>...</p>` with no extra spaces or attributes added by this function.
    - Join wrapped paragraphs with single newlines (`"\n".join(...)`), not blank lines.
    - Wrap the final HTML string in `markupsafe.Markup(...)` and return it.
    - Return type is `markupsafe.Markup` (a `str` subclass) and should be treated as safe HTML.
    - If `n <= 0`, the returned value is exactly `Markup("")`.

**Returns**:
- markupsafe.Markup | str: If `html=True`, a `Markup` string containing `n` `<p>` elements separated by `\n` (or empty `Markup` if `n <= 0`); if `html=False`, a plain `str` containing `n` paragraphs separated by `\n\n` (or empty `str` if `n <= 0`). Each paragraph is guaranteed to end with a period, and within each paragraph the same word is never repeated twice consecutively. Exceptions from invalid `min`/`max` bounds for `random.randrange(min, max)` propagate unchanged.

---

## Function: url_quote

```python
def url_quote(obj: t.Any, charset: str='utf-8', for_qs: bool=False) -> str
```

**url_quote**: Percent-encode a value for safe inclusion in a URL, optionally using query-string rules.
**Signature**: def url_quote(obj: t.Any, charset: str='utf-8', for_qs: bool=False) -> str
**Parameters**:
- obj (t.Any): Value to quote; if `bytes`, used directly; if `str`, encoded; otherwise converted to `str` then encoded.
- charset (str): Character set used to encode text to bytes when `obj` is not already `bytes`.
- for_qs (bool): If `True`, also quote `/` and convert spaces to `+` (query-string style); if `False`, leave `/` unquoted.
**Behavior**:
- If `obj` is not an instance of `bytes`:
- If `obj` is not an instance of `str`, convert it with `str(obj)`.
- Encode the resulting string to bytes using `obj.encode(charset)`.
- Determine the `safe` byte string passed to `quote_from_bytes`:
- If `for_qs` is `True`, `safe = b""`.
- Else, `safe = b"/"`.
- Call `quote_from_bytes(obj, safe)` to produce a percent-encoded string.
- If `for_qs` is `True`, replace all occurrences of `"%20"` with `"+"` in the result.
- Return the final string.
**Returns**:
- A URL-quoted string.
**Notes**:
- Only spaces encoded as `%20` are converted to `+`; other whitespace encodings are unaffected.
- Encoding errors from `obj.encode(charset)` propagate to the caller.

---

## Function: select_autoescape

```python
def select_autoescape(enabled_extensions: t.Collection[str]=('html', 'htm', 'xml'), disabled_extensions: t.Collection[str]=(), default_for_string: bool=True, default: bool=False) -> t.Callable[[str | None], bool]
```

**select_autoescape**: Build and return an autoescape-decision function that chooses whether to enable autoescaping based on a template filename’s extension.
**Signature**: def select_autoescape(enabled_extensions: t.Collection[str]=('html', 'htm', 'xml'), disabled_extensions: t.Collection[str]=(), default_for_string: bool=True, default: bool=False) -> t.Callable[[str | None], bool]
**Parameters**:
- enabled_extensions (t.Collection[str]): Collection of filename extensions for which autoescaping must be enabled; each entry may optionally start with a dot and is matched case-insensitively.
- disabled_extensions (t.Collection[str]): Collection of filename extensions for which autoescaping must be disabled; each entry may optionally start with a dot and is matched case-insensitively.
- default_for_string (bool): Value to return when the template name is None (templates created from strings).
- default (bool): Fallback value to return when the template name is not None and matches neither enabled nor disabled extensions.
**Behavior**:
- Precompute two tuples of normalized extension suffixes:
- For each string x in enabled_extensions, strip any leading '.' via lstrip('.'), lowercase it, then prefix with '.' to form a suffix like '.html'. Collect these into enabled_patterns (a tuple).
- Do the same for disabled_extensions to form disabled_patterns (a tuple).
- Define an inner function named autoescape(template_name: str | None) -> bool that closes over enabled_patterns, disabled_patterns, default_for_string, and default.
- The inner function implements the decision logic:
- If template_name is None, return default_for_string.
- Otherwise lowercase template_name.
- If the lowercased name endswith enabled_patterns (tuple-suffix check), return True.
- Else if it endswith disabled_patterns, return False.
- Else return default.
- Return the inner autoescape function.
**Returns**:
- A callable (template_name: str | None) -> bool implementing the rules above.
**Notes**:
- Matching is case-insensitive because both extensions and template_name are lowercased.
- Enabled patterns are checked before disabled patterns; if both tuples contain the same suffix, the enabled check wins because it is evaluated first.

---

## Function: autoescape

```python
def autoescape(template_name: str | None) -> bool
```

**autoescape**: Decide whether to enable autoescaping for a given template name using the rules captured by a function returned from select_autoescape.
**Signature**: def autoescape(template_name: str | None) -> bool
**Parameters**:
- template_name (str | None): Template filename to test, or None to indicate a template created from a string.
**Behavior**:
- This name refers to the inner function produced by select_autoescape.
- When called:
- If template_name is None, return the captured default_for_string value.
- Otherwise lowercase template_name.
- If the lowercased name ends with any captured enabled_patterns suffix, return True.
- Else if it ends with any captured disabled_patterns suffix, return False.
- Else return the captured default value.
**Returns**:
- True if autoescaping should be enabled, False otherwise.
**Notes**:
- The function depends on closure state (enabled_patterns, disabled_patterns, default_for_string, default) created by select_autoescape; it is not a standalone global policy by itself.

---

## Function: htmlsafe_json_dumps

```python
def htmlsafe_json_dumps(obj: t.Any, dumps: t.Callable[..., str] | None=None, **kwargs: t.Any) -> markupsafe.Markup
```

**htmlsafe_json_dumps**: JSON-serialize an object and escape specific HTML-unsafe characters using Unicode escapes, returning a Markup-safe string.
**Signature**: def htmlsafe_json_dumps(obj: t.Any, dumps: t.Callable[..., str] | None=None, **kwargs: t.Any) -> markupsafe.Markup
**Parameters**:
- obj (t.Any): The Python object to serialize with a JSON dumping function.
- dumps (t.Callable[..., str] | None): Function used to serialize obj to a JSON string; if None, use json.dumps.
- kwargs (t.Any): Arbitrary keyword arguments forwarded to the dumps function call.
**Behavior**:
- If dumps is None, set dumps to json.dumps.
- Call dumps(obj, **kwargs) to obtain a JSON text string.
- On the resulting string, perform sequential character replacements (in this exact order) to mitigate HTML/script-context hazards:
- Replace every "<" with "\\u003c".
- Replace every ">" with "\\u003e".
- Replace every "&" with "\\u0026".
- Replace every "'" with "\\u0027".
- Wrap the final replaced string in markupsafe.Markup and return it.
- No other escaping or validation is performed beyond what dumps does and the four replacements above.
**Returns**:
- markupsafe.Markup containing the JSON string with the four characters escaped as Unicode escape sequences.
**Notes**:
- The return value is marked safe for HTML rendering contexts; however, the function does not escape double quotes, so embedding into double-quoted HTML attributes requires additional escaping or different quoting.
