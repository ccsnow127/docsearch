# seqs Baseline Documentation

## Module: seqs

**Purpose**: Provides a toolbox of sequence/iterator utilities for functional-style data processing, emphasizing lazy iteration (generators/itertools) with parallel eager “list” variants (prefixed with `l`). It also wraps Python’s `map`/`filter` to accept flexible function/predicate specifications via `make_func`/`make_pred`, and re-exports several `itertools` primitives (`count`, `cycle`, `repeat`, `chain`, `accumulate`) under the module’s API.

**Key functions and roles**
- **Generation and basic access**: `repeatedly` and `iterate` build infinite (or bounded) iterators; `take`, `drop`, `first`, `second`, `nth`, `last`, `rest`, `butlast`, and `ilen` provide common sequence slicing/selection and length-by-consumption for iterables.
- **Mapping/filtering and selection**: `map`/`filter` (extended) and `lmap`/`lfilter` (list-returning) apply derived callables; `remove`/`lremove` invert filtering via `itertools.filterfalse`; `keep`/`lkeep` map then retain truthy results (or filter truthy values in one-argument form); `without`/`lwithout` exclude specific values.
- **Combining and reshaping**: `concat`/`lconcat` and `cat`/`lcat` concatenate sequences; `flatten`/`lflatten` recursively flatten nested containers based on `is_seqcont` (or a supplied `follow` predicate); `mapcat`/`lmapcat` combine mapping with concatenation; `interleave` and `interpose` weave sequences or insert separators.
- **Predicate-driven iteration and uniqueness**: `takewhile`/`dropwhile` support both explicit predicates and a one-argument “truthy” mode; `distinct`/`ldistinct` remove duplicates while preserving order, optionally using a derived key function.
- **Splitting, grouping, and counting**: `split` (lazy, via internal queues) and `lsplit` partition items by a predicate; `split_at`/`lsplit_at` and `split_by`/`lsplit_by` split by position or leading predicate-run; `group_by`, `group_by_keys`, and `group_values` build `defaultdict(list)` groupings; `count_by` and `count_reps` count occurrences into `defaultdict(int)`.
- **Windowing/partitioning**: `partition`/`lpartition` and `chunks`/`lchunks` cut data into fixed-size windows (dropping or keeping the tail) using internal `_cut` helpers that optimize for `collections.abc.Sequence` vs iterators; `partition_by`/`lpartition_by` chunk contiguous runs using `itertools.groupby`.
- **Neighborhood and zipping**: `with_prev`, `with_next`, and `pairwise` use `itertools.tee` to pair each item with its predecessor/successor/neighbor; `lzip` provides a list-returning `zip`, supporting `strict` on all Python versions (delegating to builtin strict zip on 3.10+, otherwise implementing strictness checks and errors).
- **Reductions and sums**: `reductions`/`lreductions` yield intermediate fold results (using `itertools.accumulate` when possible, with a custom `_reductions` when an initial accumulator is provided); `sums`/`lsums` specialize reductions to partial sums via `operator.add`.

---

## Function: _lmap

```python
def _lmap(f, *seqs)
```

**_lmap**: Apply a function to items from one or more iterables and return all results as a list.
**Signature**: def _lmap(f, *seqs)
**Parameters**:
- f (callable): Function applied to items; called with one argument per provided iterable.
- seqs (*iterable): One or more iterables supplying arguments to `f`, zipped in the same way as built-in `map`.
**Behavior**:
- Call the built-in `map(f, *seqs)` to create a lazy iterator of results.
- Immediately realize that iterator into memory by passing it to `list(...)`.
- Iteration stops when the shortest input iterable is exhausted (built-in `map` semantics).
- If `seqs` is empty, `map(f)` is invoked (which will raise `TypeError` under normal Python rules); this function does not intercept or alter such errors.
**Returns**:
- list: All mapped results in encounter order.
**Notes**:
- This is a thin wrapper around the built-in `map` that forces eager evaluation into a list.

---

## Function: _lfilter

```python
def _lfilter(f, seq)
```

**_lfilter**: Filter items of an iterable by a predicate and return the passing items as a list.
**Signature**: def _lfilter(f, seq)
**Parameters**:
- f (callable | None): Predicate used by built-in `filter`; if `None`, truthiness of items is used.
- seq (iterable): Source iterable to filter.
**Behavior**:
- Call the built-in `filter(f, seq)` to create a lazy iterator of items that pass.
- Immediately realize that iterator into memory by passing it to `list(...)`.
- Items are yielded/preserved in original order.
- Any exceptions raised by iterating `seq` or calling `f` propagate unchanged.
**Returns**:
- list: All items from `seq` for which the filter condition passes.
**Notes**:
- This is a thin wrapper around the built-in `filter` that forces eager evaluation into a list.

---

## Function: repeatedly

```python
def repeatedly(f, n=EMPTY)
```

**repeatedly**: Produce an iterator that repeatedly calls a zero-argument function, either infinitely or a fixed number of times.
**Signature**: def repeatedly(f, n=EMPTY)
**Parameters**:
- f (callable): A function taking no arguments; called once per produced element.
- n (object): If equal to the sentinel `EMPTY`, produce an infinite iterator; otherwise treated as the `times` argument to `itertools.repeat` (typically an int count).
**Behavior**:
- Decide repetition driver `_repeat`:
- - If `n is EMPTY`, set `_repeat = itertools.repeat(None)` (infinite stream of placeholders).
- - Else set `_repeat = itertools.repeat(None, n)` (finite stream of length `n`).
- Return a generator expression that, for each placeholder produced by `_repeat`, calls `f()` and yields its return value.
- `f()` is invoked lazily as the returned iterator is consumed.
- If `n` is not `EMPTY` and is invalid for `itertools.repeat` (e.g., non-integer where required), the underlying error propagates.
**Returns**:
- iterator: An iterator yielding `f()` results, infinite when `n is EMPTY`, otherwise of length `n`.
**Notes**:
- Side effects in `f` occur during iteration, not at creation time.

---

## Function: iterate

```python
def iterate(f, x)
```

**iterate**: Generate an infinite sequence starting from an initial value by repeatedly applying a function.
**Signature**: def iterate(f, x)
**Parameters**:
- f (callable): Unary function applied to the current value to produce the next value.
- x (object): Initial value; yielded first.
**Behavior**:
- Enter an infinite loop.
- On each iteration:
- - Yield the current `x`.
- - Update `x = f(x)`.
- The function `f` is called once per yielded element after the first.
- Any exception raised by `f` propagates and terminates the iterator.
**Returns**:
- iterator: An infinite generator yielding `x, f(x), f(f(x)), ...`.

---

## Function: take

```python
def take(n, seq)
```

**take**: Return a list containing up to the first `n` items from an iterable.
**Signature**: def take(n, seq)
**Parameters**:
- n (int): Maximum number of items to take; passed directly to `itertools.islice` as the stop value.
- seq (iterable): Source iterable.
**Behavior**:
- Create an iterator `itertools.islice(seq, n)` which yields at most `n` items from the start of `seq`.
- Convert that iterator to a list and return it.
- If `seq` has fewer than `n` items, all available items are returned.
- If `n` is 0, returns an empty list.
- Any exceptions from iterating `seq` propagate.
**Returns**:
- list: The first `n` items (or fewer if `seq` is shorter), in order.

---

## Function: drop

```python
def drop(n, seq)
```

**drop**: Skip the first `n` items of an iterable and lazily yield the remainder.
**Signature**: def drop(n, seq)
**Parameters**:
- n (int): Number of leading items to skip; passed to `itertools.islice` as the start value.
- seq (iterable): Source iterable.
**Behavior**:
- Return `itertools.islice(seq, n, None)`.
- The returned iterator consumes and discards the first `n` items from `seq` upon iteration, then yields subsequent items.
- If `seq` has fewer than `n` items, the result yields nothing.
- Any exceptions from iterating `seq` propagate.
**Returns**:
- iterator: An `islice` iterator over `seq` starting at position `n`.

---

## Function: first

```python
def first(seq)
```

**first**: Get the first item of an iterable, or `None` if it is empty.
**Signature**: def first(seq)
**Parameters**:
- seq (iterable): Source iterable.
**Behavior**:
- Obtain an iterator from `seq` via `iter(seq)`.
- Return `next(iterator, None)`:
- - If `seq` yields at least one item, return that first item.
- - If `seq` is empty, return `None`.
- Consumes at most one item from `seq`.
**Returns**:
- object | None: The first element, or `None` when no elements exist.

---

## Function: second

```python
def second(seq)
```

**second**: Get the second item of an iterable, or `None` if fewer than two items exist.
**Signature**: def second(seq)
**Parameters**:
- seq (iterable): Source iterable.
**Behavior**:
- Compute `rest(seq)` (which skips the first item and yields the remainder).
- Return `first(rest(seq))`:
- - If `seq` has at least two items, this returns the second.
- - If `seq` has zero or one item, this returns `None`.
- This operation may consume up to two items from an iterator input.
**Returns**:
- object | None: The second element, or `None` if it does not exist.

---

## Function: nth

```python
def nth(n, seq)
```

**nth**: Get the nth item (0-based) from a sequence or iterable, or `None` if it does not exist.
**Signature**: def nth(n, seq)
**Parameters**:
- n (int): Zero-based index of the desired element.
- seq (Sequence | iterable): Source; may support direct indexing or only iteration.
**Behavior**:
- First attempt indexed access `seq[n]`.
- If indexed access succeeds, return that value.
- If `seq[n]` raises `IndexError`, return `None` (index out of range).
- If `seq[n]` raises `TypeError` (e.g., `seq` is not subscriptable), fall back to iteration:
- - Use `itertools.islice(seq, n, None)` to skip the first `n` items.
- - Return `next(islice_iterator, None)`.
- For iterator inputs, this consumes up to `n+1` items to determine the result.
**Returns**:
- object | None: The element at index `n`, or `None` if no such element exists.

---

## Function: last

```python
def last(seq)
```

**last**: Get the last item from a sequence or iterable, or `None` if it is empty.
**Signature**: def last(seq)
**Parameters**:
- seq (Sequence | iterable): Source; may support negative indexing or only iteration.
**Behavior**:
- First attempt to return `seq[-1]`.
- If `seq[-1]` succeeds, return that value.
- If `seq[-1]` raises `IndexError`, return `None` (empty sequence).
- If `seq[-1]` raises `TypeError` (e.g., `seq` is not subscriptable), compute the last element by consuming the iterable:
- - Initialize `item = None`.
- - Iterate `for item in seq: pass`, repeatedly overwriting `item` with each yielded value.
- - After the loop:
- - - If at least one element was seen, `item` holds the final element; return it.
- - - If no elements were seen, `item` remains `None`; return `None`.
- For iterator inputs, this fully consumes `seq`.
**Returns**:
- object | None: The last element, or `None` if `seq` is empty.
**Notes**:
- When `seq` is an iterator, calling `last` exhausts it.

---

## Function: rest

```python
def rest(seq)
```

**rest**: Return an iterator over all items of `seq` except the first.
**Signature**: def rest(seq)
**Parameters**:
- seq (<any iterable>): Input sequence/iterable whose first element will be skipped.
**Behavior**:
- Create and return an iterator that skips exactly the first item of `seq` and then yields every subsequent item in order.
- The returned value is lazy: it does not consume `seq` until iterated.
- If `seq` is empty, the returned iterator yields no items.
- Implemented by delegating to `drop(1, seq)` (i.e., an `itertools.islice(seq, 1, None)`-style iterator).
**Returns**:
- An iterator yielding all elements of `seq` starting from index 1 (the second element), or an empty iterator if `seq` has fewer than 2 elements.
**Notes**:
- Because it is lazy, if `seq` is an iterator it will be advanced when the result is consumed.
- Any exceptions raised by iterating `seq` propagate during iteration of the returned iterator.

---

## Function: butlast

```python
def butlast(seq)
```

**butlast**: Yield all elements of `seq` except the last one.
**Signature**: def butlast(seq)
**Parameters**:
- seq (<any iterable>): Input sequence/iterable to traverse while omitting its final element.
**Behavior**:
- Convert `seq` to an iterator `it = iter(seq)`.
- Attempt to read the first element from `it`:
- - If `seq` is empty (raises `StopIteration`), yield nothing and terminate.
- - Otherwise store that first element as `prev`.
- Iterate through the remaining elements of `it` one by one:
- - For each `item` obtained, yield the previous element `prev`.
- - Then set `prev = item` and continue.
- When the iterator is exhausted, stop without yielding the final stored `prev` (thereby omitting the last element of the original sequence).
- The function is lazy and yields items as it reads ahead by one element.
**Returns**:
- An iterator (generator) yielding all items of `seq` except the last; yields nothing if `seq` has length 0 or 1.
**Notes**:
- Requires reading one element ahead, so it will consume `seq` as it yields.
- Any exceptions raised by iterating `seq` propagate during iteration of the generator.

---

## Function: ilen

```python
def ilen(seq)
```

**ilen**: Count the number of items in an iterable by consuming it without materializing it into a list.
**Signature**: def ilen(seq)
**Parameters**:
- seq (<any iterable>): Iterable to be fully consumed and counted.
**Behavior**:
- Create an infinite counter iterator `counter = itertools.count()`.
- Consume `seq` by zipping it with `counter` and feeding the zip iterator into a `collections.deque` with `maxlen=0`:
- - `zip(seq, counter)` advances `counter` once per element pulled from `seq`.
- - `deque(..., maxlen=0)` discards all produced pairs immediately, forcing full consumption efficiently.
- After consumption completes, return `next(counter)`:
- - Because `counter` started at 0 and was advanced once per element, `next(counter)` yields the total number of consumed elements.
- This fully exhausts `seq`.
**Returns**:
- An integer equal to the number of items produced by `seq`.
**Notes**:
- Side effect: `seq` is exhausted; if it is an iterator, it cannot be reused.
- Any exceptions raised while iterating `seq` propagate; in that case the count may be partial and no value is returned.

---

## Function: lmap

```python
def lmap(f, *seqs)
```

**lmap**: Apply a flexible “function specification” to items from one or more input iterables (in parallel) and return the mapped results as a list.

**Signature**: def lmap(f: object, *seqs: object) -> list

**Parameters**:
- f (object): Function/mapper specification. It is normalized to a callable by `make_func(f)` (see “Function specification” rules below).
- seqs (object): One or more iterables to map over in parallel (like built-in `map`). Each iteration pulls one item from each iterable.

**Behavior**:
- Convert the mapper specification `f` into a callable `func` by calling `make_func(f)`.
- Apply Python’s built-in `map` (captured as `_map` at import time) to `func` and the provided iterables: `_map(func, *seqs)`.
- Materialize the mapped iterator into a list and return it.
- Mapping stops when the shortest input iterable is exhausted (built-in `map` semantics).
- Any exception raised by `make_func`, by calling the resulting mapper, or by iterating any input iterable propagates.
- This function is eager: it fully consumes the mapped iterator to build the list.

- Function specification (what `make_func(f)` must accept and what it means):
  - Callable:
    - If `f` is callable, `make_func(f)` returns `f` unchanged (or a wrapper with identical call semantics).
  - None (identity):
    - If `f is None`, it is treated as the identity function: it returns its first positional argument unchanged. (When mapping over multiple sequences, the identity function returns the first sequence’s element.)
  - String (attribute/key access shortcut):
    - If `f` is a `str`, it denotes a single-step accessor applied to a value `x`.
    - Access rule (precise fallback/propagation contract):
      - First, attempt key-style access: evaluate `x[f]`.
      - If key-style access succeeds, return that value.
      - If key-style access fails because the object does not support that form of access (i.e., `x` is not subscriptable with a string key), then fall back to attribute access and return `getattr(x, f)`.
      - If key-style access fails because the key is missing or invalid for an object that does support key/indexing semantics, the exception must propagate and no attribute fallback is attempted.
    - Exception classification for the above rule:
      - Exceptions that indicate “no such key / invalid key for this object’s indexing semantics” must propagate (no fallback). This includes, but is not limited to, `KeyError` and `IndexError` (and any domain-specific subclass used to report missing keys/indices).
      - Only exceptions that indicate “this access mode is not supported for this object” should trigger the attribute fallback. This commonly includes `TypeError` raised due to an unsupported subscript operation or unsupported key type for a non-mapping object.
      - If the fallback to `getattr(x, f)` is attempted and the attribute does not exist, the resulting `AttributeError` propagates.
    - Invariants implied by this contract:
      - The string form is an accessor, not an expression evaluator.
      - Objects that are subscriptable (including sequences/strings) are treated as supporting `x[•]`; therefore missing/invalid lookups that raise `IndexError`/`KeyError` (or equivalents) must not be converted into attribute access attempts.
  - Integer (positional item access):
    - If `f` is an `int`, it denotes positional indexing:
      - When applied to a value `x`, it returns `x[f]`.
      - Indexing errors (including `IndexError`, `KeyError`, `TypeError`, etc., as raised by `x.__getitem__`) propagate; no attribute fallback is performed for integer specs.
  - Sequence of keys/indices (multi-get / projection):
    - If `f` is a `list` or `tuple`, it denotes a projection:
      - When applied to a value `x`, it returns a tuple consisting of `x[k]` for each element `k` in `f`, in order.
      - Each element `k` may itself be a valid single-step key/index (commonly `str` or `int`); failures propagate.
      - Projection uses direct `__getitem__` for each `k` (i.e., it does not apply the string accessor’s attribute-fallback rule per element unless the element itself is interpreted as a string-step in a path; see “Dict (path/composition spec)” below).
  - Dict (path/composition spec):
    - If `f` is a `dict`, it is a structured function specification. Dict specs are reserved and are not treated as “arbitrary mappings to be returned”; `make_func` must interpret supported dict shapes and raise `TypeError` only when the dict does not match any supported shape.
    - Dict specs fall into two broad categories: “path dicts” (access a value through a chain of steps) and “composition dicts” (combine/compose other function specs).
    - Recognition and disambiguation rules (must be deterministic):
      - If the dict contains any recognized path-key (see “Recognized path keys”), it is a path dict and the associated value defines the path steps.
      - Otherwise, if the dict contains any recognized composition-key (see “Recognized composition keys”), it is a composition dict and the associated values define nested function specs.
      - Otherwise, the dict is unsupported and `make_func` must raise `TypeError` indicating an unsupported dict function specification (it must not guess a schema beyond the recognized keys).
    - Recognized path keys (synonyms):
      - Any of the following keys, if present, indicate a path dict: `"path"`, `"steps"`, `"get"`, `"in"`.
      - Exactly one of these keys must be used per dict spec; if multiple are present, `make_func` may raise `TypeError` for ambiguity.
    - Path steps value types:
      - The value associated with the chosen path key must be either:
        - A `list` or `tuple` of step specifications (a multi-step path), or
        - A single step specification (equivalent to a one-element path).
      - A “step specification” in a path may be any of:
        - `str` (string-step): apply the “String (attribute/key access shortcut)” rules to the current value.
        - `int` (index-step): apply the “Integer (positional item access)” rules to the current value.
        - `list` or `tuple` (projection-step): treat this step as a projection applied to the current value, returning a tuple of `current[k]` for each element `k` in the list/tuple; errors propagate.
        - `dict` (nested spec-step): the dict is interpreted recursively as a function specification via `make_func` and applied to the current value (i.e., nested dicts can represent a sub-path or a composition that transforms the current value before continuing).
        - Any callable (call-step): call it with the current value as its sole positional argument.
      - Any other step type is unsupported and must cause `TypeError`.
    - Path evaluation algorithm:
      - The function produced by a path dict accepts the same positional arguments as `map` supplies; it uses only the first positional argument as the initial “current value” (unless the dict is itself nested inside a higher-order spec that passes different values).
      - Initialize `cur` to the first positional argument.
      - For each step in order:
        - If the step is `str`, apply the string-step access contract (key access with attribute fallback only when the object does not support that access mode; missing keys propagate).
        - If the step is `int`, return `cur[step]` with normal propagation of `__getitem__` errors.
        - If the step is a `list`/`tuple`, return a tuple of `cur[k]` for each `k` in the step, in order; errors propagate.
        - If the step is a `dict`, recursively build a callable `g = make_func(step)` and set `cur = g(cur)`.
        - If the step is callable, set `cur = step(cur)`.
      - Return the final `cur`.
      - Any error at any step propagates immediately; errors from deeper steps must not be masked by attempting alternative access modes for earlier steps beyond the specified fallback rules.
    - Recognized composition keys (synonyms):
      - Any of the following keys, if present (and no recognized path key is present), indicate a composition dict:
        - `"call"`: call a nested function spec with arguments produced by nested specs.
        - `"compose"`: compose multiple function specs into one (right-to-left application).
        - `"juxt"`: apply multiple function specs to the same input and return a tuple of results.
      - Composition dicts must not be treated as paths unless they also contain a recognized path key (in which case the dict is ambiguous and may raise `TypeError`).
    - Composition dict semantics:
      - `"compose"`:
        - Value must be a `list`/`tuple` of one or more function specifications.
        - The resulting function applies them right-to-left: `compose([f1, f2, f3])(x) == f1(f2(f3(x)))`.
        - Each element is normalized via `make_func`.
        - The composed function accepts `*args` from `map`; the rightmost function receives those `*args`, and each subsequent function receives the single value returned by the previous function.
      - `"juxt"`:
        - Value must be a `list`/`tuple` of one or more function specifications.
        - The resulting function applies each normalized function to the same incoming `*args` and returns a tuple of results in the same order.
      - `"call"`:
        - Value must be a `dict` with:
          - `"fn"`: a function specification resolving to a callable.
          - `"args"` (optional): a `list`/`tuple` of function specifications; each is applied to the incoming `*args` to produce one positional argument for the call.
          - `"kwargs"` (optional): a `dict` mapping keyword names (`str`) to function specifications; each spec is applied to the incoming `*args` to produce the keyword value.
        - The resulting function evaluates `"fn"` to a callable `h`, evaluates each `"args"` spec to build positional arguments, evaluates each `"kwargs"` spec to build keyword arguments, then calls `h(*pos_args, **kw_args)`.
        - If `"args"` is omitted, the call uses no additional positional arguments (i.e., calls `h()`), unless the `"fn"` itself is a callable that closes over needed values.
        - If `"kwargs"` is omitted, no keyword arguments are passed.
      - Any missing required keys, wrong value types, or unsupported nested specs must raise `TypeError`.
  - Composition / higher-order specifications (non-dict containers):
    - If `f` is a container that encodes composition (e.g., a tuple/list where the first element indicates a combinator and remaining elements are nested function specifications), `make_func` may support composing/combining the nested specs into a single callable.
    - Composition is resolved entirely inside `make_func`; `lmap` treats the result as an ordinary callable.
  - General invariants for `make_func` outputs:
    - The returned `func` must be callable and accept the same positional arguments that built-in `map` will supply (one argument per input iterable).
    - `func` is called once per “row” of items drawn from `seqs`.
    - `make_func` may raise `TypeError` for unsupported specifications; `lmap` does not catch or transform this error.

**Returns**:
- list: A list containing the mapped values in iteration order.

---

## Function: lfilter

```python
def lfilter(pred, seq)
```

**lfilter**: Filter a sequence using an extended predicate and return the passing items as a list.
**Signature**: def lfilter(pred, seq)
**Parameters**:
- pred (<any>): Predicate specification; converted to a callable via `make_pred(pred)`.
- seq (<iterable>): Iterable whose items will be tested.
**Behavior**:
- Convert `pred` into a callable predicate by calling `make_pred(pred)`.
- Apply Python’s built-in `filter` (captured as `_filter` at import time) to the predicate and `seq`.
- Materialize the filtered results into a list and return it.
- Items are included if the predicate returns a truthy value.
**Returns**:
- A `list` of items from `seq` for which the derived predicate is truthy, preserving original order.
**Notes**:
- Any exceptions raised by `make_pred`, by calling the predicate, or by iterating `seq` propagate.
- This function eagerly consumes `seq` to build the list.

---

## Function: map

```python
def map(f, *seqs)
```

**map**: Apply an extended mapping function over one or more sequences, returning a lazy iterator like built-in `map`.
**Signature**: def map(f, *seqs)
**Parameters**:
- f (<any>): Mapper specification; converted to a callable via `make_func(f)`.
- seqs (tuple[<iterable>, ...]): One or more iterables to map over in parallel.
**Behavior**:
- Convert `f` into a callable mapper by calling `make_func(f)`.
- Return the result of applying the original built-in `map` (stored as `_map`) to the callable and `*seqs`.
- The returned object is lazy and yields mapped values on iteration.
- Iteration stops when the shortest input iterable is exhausted (built-in `map` semantics).
**Returns**:
- A `map` iterator producing `callable(item1, item2, ...)` for each parallel tuple of items.
**Notes**:
- Any exceptions raised by `make_func` occur immediately; exceptions from iterating inputs or calling the mapper occur during iteration of the returned iterator.

---

## Function: filter

```python
def filter(pred, seq)
```

**filter**: Filter a sequence using an extended predicate, returning a lazy iterator like built-in `filter`.
**Signature**: def filter(pred, seq)
**Parameters**:
- pred (<any>): Predicate specification; converted to a callable via `make_pred(pred)`.
- seq (<iterable>): Iterable whose items will be tested.
**Behavior**:
- Convert `pred` into a callable predicate by calling `make_pred(pred)`.
- Return the result of applying the original built-in `filter` (stored as `_filter`) to the predicate and `seq`.
- The returned object is lazy and yields items from `seq` whose predicate result is truthy.
**Returns**:
- A `filter` iterator yielding items from `seq` that satisfy the derived predicate, preserving order.
**Notes**:
- Any exceptions raised by `make_pred` occur immediately; exceptions from iterating `seq` or calling the predicate occur during iteration of the returned iterator.

---

## Function: lremove

```python
def lremove(pred, seq)
```

**lremove**: Return a list of items from `seq` that do not satisfy the given predicate.
**Signature**: def lremove(pred, seq)
**Parameters**:
- pred (<any>): Predicate specification; converted to a callable via `make_pred(pred)`.
- seq (<iterable>): Iterable to filter.
**Behavior**:
- Call `remove(pred, seq)` to obtain a lazy iterator of items to keep (those for which the predicate is falsy).
- Convert that iterator to a list and return it.
- Order of remaining items is preserved.
**Returns**:
- A `list` of items from `seq` for which the derived predicate is falsy.
**Notes**:
- Eagerly consumes `seq` to build the list.
- Any exceptions raised by predicate derivation, predicate evaluation, or iteration propagate.

---

## Function: remove

```python
def remove(pred, seq)
```

**remove**: Lazily iterate items from `seq` that do not satisfy the given predicate.
**Signature**: def remove(pred, seq)
**Parameters**:
- pred (<any>): Predicate specification; converted to a callable via `make_pred(pred)`.
- seq (<iterable>): Iterable to filter.
**Behavior**:
- Convert `pred` into a callable predicate by calling `make_pred(pred)`.
- Return `itertools.filterfalse(predicate, seq)`:
- - For each item in `seq`, evaluate the predicate.
- - Yield the item only when the predicate result is falsy.
- The returned iterator is lazy and preserves input order.
**Returns**:
- An iterator yielding items from `seq` for which the derived predicate is falsy.
**Notes**:
- Exceptions from `make_pred` occur immediately; exceptions from iterating `seq` or calling the predicate occur during iteration.

---

## Function: lkeep

```python
def lkeep(f, seq=EMPTY)
```

**lkeep**: Map a sequence with `f` and return a list of only the truthy mapped results; in one-argument form, list only truthy values from an iterable.
**Signature**: def lkeep(f, seq=EMPTY)
**Parameters**:
- f (<any>): If `seq` is provided, a mapper applied to each element (via `keep`); if `seq` is omitted, this is treated as the iterable of values to filter by truthiness.
- seq (<any>, default EMPTY): Sentinel-controlled optional iterable; when omitted (i.e., equals `EMPTY`), `f` is treated as the iterable.
**Behavior**:
- Delegate to `keep(f, seq)` to obtain an iterator of truthy values.
- Materialize that iterator into a list and return it.
- Two modes (determined solely by whether `seq is EMPTY`):
- - If `seq is EMPTY`: `keep` will filter the iterable `f` by `bool`, yielding only truthy elements.
- - Else: `keep` will map `f` over `seq` (using the module’s extended `map`) and then filter the mapped results by `bool`, yielding only truthy mapped values.
**Returns**:
- A `list` of truthy values produced by `keep(f, seq)`.
**Notes**:
- Eagerly consumes the underlying iterator to build the list.
- Any exceptions raised by mapping, predicate evaluation (`bool`), or iteration propagate.

---

## Function: keep

```python
def keep(f, seq=EMPTY)
```

**keep**: Map items through a function and yield only truthy results, or (in 1-argument form) filter an iterable by truthiness.
**Signature**: def keep(f, seq=EMPTY)
**Parameters**:
- f (<any>): If `seq` is provided, a mapper accepted by this module’s extended `map()` (i.e., passed as-is to `map(f, seq)`); if `seq` is omitted (left as `EMPTY`), this is treated as the iterable to be filtered by truthiness.
- seq (<any>): Either an iterable to map over, or the sentinel `EMPTY` meaning “1-argument form”.
**Behavior**:
- If `seq is EMPTY` (1-argument form):
- Treat `f` as an iterable.
- Return an iterator equivalent to `filter(bool, f)` (i.e., yield each element of `f` whose truth value is `True`).
- Else (2-argument form):
- Create a mapped iterator by calling this module’s extended `map(f, seq)`.
- Return an iterator equivalent to `filter(bool, mapped)`.
- No eager evaluation is performed; results are produced lazily as the returned iterator is consumed.
**Returns**:
- An iterator yielding only truthy values: either truthy elements of `f` (1-argument form) or truthy results of applying `f` to each element of `seq` (2-argument form).
**Notes**:
- Truthiness is determined by Python’s `bool()`.
- In 2-argument form, mapping uses this module’s `map`, not the built-in, so `f` may be a “funcy” mapper spec handled by `make_func` inside `map()`.

---

## Function: without

```python
def without(seq, *items)
```

**without**: Lazily yield items from a sequence excluding any that match a provided set of forbidden values.
**Signature**: def without(seq, *items)
**Parameters**:
- seq (<any>): An iterable to scan in order.
- items (tuple[<any>, ...]): Values to exclude; membership is tested with `value not in items`.
**Behavior**:
- Iterate over `seq` in encounter order.
- For each `value`:
- If `value` is not equal to any element in `items` (via the tuple membership test `value not in items`), yield `value`.
- Otherwise, skip it.
- Processing is lazy; the input is consumed only as the output iterator is consumed.
**Returns**:
- A generator/iterator yielding the elements of `seq` except those that are members of `items`.
**Notes**:
- Membership is checked against the `items` tuple, so complexity is linear in `len(items)` per element.
- Equality semantics are those of Python’s `in` on a tuple (uses `==` comparisons).

---

## Function: lwithout

```python
def lwithout(seq, *items)
```

**lwithout**: Eagerly remove specified values from a sequence while preserving order.
**Signature**: def lwithout(seq, *items)
**Parameters**:
- seq (<any>): An iterable to scan in order.
- items (tuple[<any>, ...]): Values to exclude; forwarded to `without`.
**Behavior**:
- Call `without(seq, *items)` to obtain a lazy iterator of allowed values.
- Convert that iterator to a list with `list(...)`.
**Returns**:
- A list containing all elements of `seq` except those present in `items`, in original order.
**Notes**:
- This fully consumes `seq`.

---

## Function: lconcat

```python
def lconcat(*seqs)
```

**lconcat**: Eagerly concatenate multiple iterables into a single list, preserving encounter order.

**Signature**: def lconcat(*seqs: object) -> list

**Parameters**:
- seqs (object): Any number of iterables to concatenate in the given order.

**Behavior**:
- Interpret each positional argument in seqs as a distinct iterable to be concatenated; lconcat does not recursively flatten or otherwise descend into elements yielded by those iterables.
- Create a single logical traversal over all provided iterables in order, equivalent to iterating `itertools.chain(*seqs)`.
- Materialize the traversal into a new list by consuming all items from the first iterable until exhaustion, then the second, and so on, appending each yielded element to the result list in encounter order.
- Eager consumption and termination:
  - If any input is a one-shot iterator/generator, it will be exhausted as part of building the result list.
  - If any input is infinite (or never terminates), lconcat will not terminate.
- Error propagation and partial consumption:
  - If any element of seqs is not iterable, raise the same exception normal iteration would raise (typically TypeError) when iteration is attempted.
  - If iterating any input raises an exception, the exception propagates; earlier iterables may already have been partially or fully consumed and the result list may be partially built but is not returned.
- Non-goals:
  - lconcat performs no recursion and requires no cycle detection by itself.

**Behavior (hard contract for flatten and lflatten in the same module)**:
- Scope and intent:
  - This contract applies specifically and test-enforced to the module’s recursive flattening utilities named `flatten` and `lflatten` (and any equivalent aliases/wrappers in the same module).
  - lconcat itself does not implement this behavior, but the module is required to implement it correctly for `flatten`/`lflatten`.
- Mandatory cycle-handling strategy for `flatten`/`lflatten` (must implement exactly this strategy):
  - Use active-path detection (not a global “visited” set): track the identities of containers currently being descended into (the current recursion/expansion stack).
  - Maintain an `active` set (or equivalent) containing `id(obj)` for each container currently on the active descent path.
  - Before descending into a candidate container `obj`, `flatten`/`lflatten` must check whether `id(obj)` is already present in `active`.
    - If present, a cycle has been detected along the current path.
- Mandatory behavior on cycle detection for `flatten`/`lflatten` (must implement exactly this behavior):
  - On detecting a cycle via the active-path check, do not descend further into that container.
  - Treat that container object as atomic at that point: yield/emit the container object itself as a single element in the flattened output, in the position where it is encountered, and continue traversal.
  - Cycle handling must not raise an exception; cycles must terminate via this “treat as atomic” rule.
- Active-path bookkeeping requirements for `flatten`/`lflatten`:
  - When descending into a container `obj`, add `id(obj)` to `active` before iterating its contents.
  - Ensure `id(obj)` is removed from `active` after finishing that container, even if an exception occurs while iterating its contents (i.e., removal must be in a `finally`-equivalent cleanup path).
  - The `active` set must represent only the current descent stack; once a container is fully processed and removed, encountering the same container later via a different branch may be descended into again (subject to the same cycle check on that new active path).
- Minimal required control flow for `flatten`/`lflatten` (pseudocode-level contract; variable names may differ):
  - If an item is not flattenable under the module’s predicate (including explicit exclusions), yield it as-is.
  - Else the item is flattenable:
    - If `id(item)` is in `active`: yield `item` as a single element and do not recurse/descend.
    - Else:
      - Add `id(item)` to `active`.
      - Iterate the item’s elements left-to-right; for each element, apply the same flattening rules depth-first.
      - Remove `id(item)` from `active` when done (guaranteed cleanup).
- Recursion-depth is not a cycle-handling mechanism:
  - `flatten`/`lflatten` must not rely on Python recursion limits or eventual `RecursionError` to stop cyclic traversal.
  - Termination on cyclic/self-referential graphs must be guaranteed by explicit identity-based active-path detection as described above.
- Flattenable definition must be precise and must include explicit exclusions (must be implemented as documented by the module):
  - `flatten`/`lflatten` must clearly define which objects are considered “flattenable containers” (eligible for recursive descent) and implement that definition exactly.
  - Regardless of the broader definition, `flatten`/`lflatten` must explicitly treat string-like and bytes-like objects as atomic (never descended into), including at least: `str`, `bytes`, and `bytearray`.
  - If `flatten`/`lflatten` flattens over general `collections.abc.Iterable`, it must explicitly exclude additional iterable-but-atomic categories as documented by the module (commonly including mappings such as `dict`/`collections.abc.Mapping`, and any other iterables that should not be descended into).
- Ordering and traversal invariants for `flatten`/`lflatten`:
  - Traversal must be left-to-right and depth-first with respect to the chosen flattenable containers, preserving encounter order of elements as they are visited.
  - When a container is treated as atomic (due to type exclusions or cycle detection), it must appear in the output sequence exactly where it is encountered in the traversal, as a single element.
- Side effects and consumption notes for `flatten`/`lflatten`:
  - If `flatten`/`lflatten` accepts iterators/generators as inputs and chooses to descend into them (if they are considered flattenable by its predicate), it may consume them; such consumption must be consistent with its documented flattenable definition and exclusions.
  - Cycle detection is based on container identity (`id`), not equality; distinct containers with equal contents are treated independently.

**Returns**:
- A list containing all items from the first iterable, then all from the second, and so on, in the order encountered.

---

## Function: lcat

```python
def lcat(seqs)
```

**lcat**: Eagerly concatenate a single iterable of iterables into one list.
**Signature**: def lcat(seqs)
**Parameters**:
- seqs (<any>): An iterable whose elements are themselves iterables.
**Behavior**:
- Concatenate the inner iterables in encounter order (equivalent to `itertools.chain.from_iterable(seqs)`).
- Materialize the result into a list.
**Returns**:
- A list containing all items from each inner iterable, in order.
**Notes**:
- Fully consumes `seqs` and each inner iterable.

---

## Function: flatten

```python
def flatten(seq, follow=is_seqcont)
```

**flatten**: Lazily flatten an arbitrarily nested structure by recursively expanding items that satisfy a predicate.
**Signature**: def flatten(seq, follow=is_seqcont)
**Parameters**:
- seq (<any>): An iterable of items, some of which may themselves be iterable “containers” to recurse into.
- follow (callable): A predicate called as `follow(item)`; if truthy, `item` is treated as a nested sequence to flatten recursively.
**Behavior**:
- Iterate through `seq` in order.
- For each `item`:
- If `follow(item)` is truthy:
- Recursively iterate over `flatten(item, follow)` and yield each of its yielded values (depth-first traversal).
- Else:
- Yield `item` as-is.
- The traversal is lazy and recursive; it yields values as soon as they are discovered.
**Returns**:
- A generator/iterator yielding a depth-first flattened stream of values.
**Notes**:
- The default `follow` is `is_seqcont` (from this package), which determines what kinds of objects are considered “sequence containers” to descend into.
- If `follow` returns true for an object that is self-referential or leads to cycles, recursion may not terminate.

---

## Function: lflatten

```python
def lflatten(seq, follow=is_seqcont)
```

**lflatten**: Eagerly flatten an arbitrarily nested structure into a list.
**Signature**: def lflatten(seq, follow=is_seqcont)
**Parameters**:
- seq (<any>): An iterable potentially containing nested iterables.
- follow (callable): Predicate controlling whether to recurse into an item; forwarded to `flatten`.
**Behavior**:
- Call `flatten(seq, follow)` to produce a lazy flattened iterator.
- Convert the iterator to a list.
**Returns**:
- A list of all flattened values in the same order `flatten` would yield.
**Notes**:
- Fully consumes the input and all nested iterables that are followed.

---

## Function: lmapcat

```python
def lmapcat(f, *seqs)
```

**lmapcat**: Map one or more sequences and eagerly concatenate (flatten one level) the mapped results into a list.
**Signature**: def lmapcat(f, *seqs)
**Parameters**:
- f (<any>): A mapper accepted by this module’s extended `map()`; applied elementwise across `seqs`.
- seqs (tuple[<any>, ...]): One or more iterables to be mapped in parallel (like `map`).
**Behavior**:
- Apply this module’s `map(f, *seqs)` to produce an iterator of mapped results.
- Treat each mapped result as an iterable and concatenate them in order using `lcat(...)`.
- Materialize the concatenation into a list.
**Returns**:
- A list containing all items from each iterable produced by the mapping, concatenated in mapped order.
**Notes**:
- This is a one-level “map then concatenate” (not a deep flatten).
- Fully consumes the mapped results and their contents.

---

## Function: mapcat

```python
def mapcat(f, *seqs)
```

**mapcat**: Map one or more sequences and lazily chain (flatten one level) the mapped results.
**Signature**: def mapcat(f, *seqs)
**Parameters**:
- f (<any>): A mapper accepted by this module’s extended `map()`; applied elementwise across `seqs`.
- seqs (tuple[<any>, ...]): One or more iterables to be mapped in parallel (like `map`).
**Behavior**:
- Apply this module’s `map(f, *seqs)` to produce an iterator of mapped results.
- Treat each mapped result as an iterable and chain them in order using `cat(...)` (i.e., `itertools.chain.from_iterable`).
- Yield items lazily from the chained inner iterables.
**Returns**:
- An iterator yielding the concatenated contents of each iterable produced by the mapping.
**Notes**:
- This is a one-level “map then concatenate” (not a deep flatten).
- Stops when the shortest input sequence to `map` is exhausted (standard `map` behavior).

---

## Function: interleave

```python
def interleave(*seqs)
```

**interleave**: Lazily yield items by alternating between multiple sequences position-by-position.
**Signature**: def interleave(*seqs)
**Parameters**:
- seqs (tuple[<any>, ...]): Two or more iterables to interleave; may be any iterables accepted by `zip`.
**Behavior**:
- Zip the sequences together with `zip(*seqs)`, producing tuples of the i-th elements.
- Concatenate (flatten one level) those tuples into a single stream using `cat(...)` (chain-from-iterable).
- Yield elements in the order: first element of each sequence, then second element of each sequence, etc.
- Interleaving stops as soon as `zip` stops, i.e., when the shortest input iterable is exhausted.
**Returns**:
- An iterator yielding the interleaved elements.
**Notes**:
- Because it is based on `zip`, extra trailing elements in longer sequences are ignored.

---

## Function: interpose

```python
def interpose(sep, seq)
```

**interpose**: Yield items from a sequence with a separator value inserted between consecutive items.
**Signature**: def interpose(sep, seq)
**Parameters**:
- sep (Any): Value to insert between items of `seq`.
- seq (Iterable[Any]): Input iterable whose items will be yielded with separators interleaved.
**Behavior**:
- Create an infinite iterator that repeats `sep`.
- Interleave that repeating-separator iterator with `seq` by alternating one item from each (i.e., `sep, item0, sep, item1, ...` until `seq` is exhausted).
- Drop the very first yielded element from that interleaving (which is the leading `sep`).
- Yield the remaining elements lazily.
- If `seq` is empty, the interleaving produces no items from `seq`; after dropping the first element, the resulting iterator yields nothing.
- If `seq` has one item, the result yields just that item (no separators).
**Returns**:
- Iterator[Any]: A lazy iterator producing `item0, sep, item1, sep, ...` with no trailing separator.

---

## Function: takewhile

```python
def takewhile(pred, seq=EMPTY)
```

**takewhile**: Yield items from the start of an iterable while a predicate holds, with a one-argument mode that stops on the first falsy item.
**Signature**: def takewhile(pred, seq=EMPTY)
**Parameters**:
- pred (Any): Either a predicate spec (converted to a callable predicate) when `seq` is provided, or the input iterable itself when `seq is EMPTY`.
- seq (Iterable[Any] | EMPTY): Optional input iterable; if omitted (left as `EMPTY`), `pred` is treated as the iterable and the predicate becomes `bool`.
**Behavior**:
- If `seq is EMPTY`:
- Treat `pred` as the input iterable (`seq = pred`).
- Use `bool` as the predicate.
- Else:
- Convert `pred` to a callable predicate using `make_pred(pred)`.
- Return an iterator equivalent to `itertools.takewhile(predicate, seq)`:
- Iterate `seq` from the start.
- Yield each item while `predicate(item)` is truthy.
- Stop immediately (and permanently) at the first item for which `predicate(item)` is falsy; that failing item is not yielded.
- Evaluation is lazy; items are consumed from `seq` only as the returned iterator is advanced.
**Returns**:
- Iterator[Any]: Items from the start of `seq` up to (but not including) the first predicate failure.

---

## Function: dropwhile

```python
def dropwhile(pred, seq=EMPTY)
```

**dropwhile**: Skip initial items of an iterable while a predicate holds, then yield the remainder, with a one-argument mode that skips initial truthy items.
**Signature**: def dropwhile(pred, seq=EMPTY)
**Parameters**:
- pred (Any): Either a predicate spec (converted to a callable predicate) when `seq` is provided, or the input iterable itself when `seq is EMPTY`.
- seq (Iterable[Any] | EMPTY): Optional input iterable; if omitted (left as `EMPTY`), `pred` is treated as the iterable and the predicate becomes `bool`.
**Behavior**:
- If `seq is EMPTY`:
- Treat `pred` as the input iterable (`seq = pred`).
- Use `bool` as the predicate.
- Else:
- Convert `pred` to a callable predicate using `make_pred(pred)`.
- Return an iterator equivalent to `itertools.dropwhile(predicate, seq)`:
- Consume and discard items from the start of `seq` while `predicate(item)` is truthy.
- Once the first falsy item is encountered, yield that item and then yield all subsequent items from `seq` without further predicate checks.
- Evaluation is lazy; items are consumed from `seq` only as the returned iterator is advanced.
**Returns**:
- Iterator[Any]: An iterator over `seq` starting from the first item that does not satisfy the predicate (inclusive).

---

## Function: ldistinct

```python
def ldistinct(seq, key=EMPTY)
```

**ldistinct**: Remove duplicates from an iterable while preserving first-occurrence order, returning a list.
**Signature**: def ldistinct(seq, key=EMPTY)
**Parameters**:
- seq (Iterable[Any]): Input iterable.
- key (Any | EMPTY): Optional key function spec used to determine uniqueness; if `EMPTY`, uniqueness is based on the items themselves.
**Behavior**:
- Call `distinct(seq, key)` to produce a lazy stream of unique items (preserving order).
- Materialize that stream into a list and return it.
- All behavior regarding how uniqueness is computed (including key handling and hashability requirements) matches `distinct`.
**Returns**:
- list[Any]: The unique items from `seq` in their original order.

---

## Function: distinct

```python
def distinct(seq, key=EMPTY)
```

**distinct**: Lazily iterate over an iterable, yielding only the first occurrence of each unique item (or unique key), preserving order.
**Signature**: def distinct(seq, key=EMPTY)
**Parameters**:
- seq (Iterable[Any]): Input iterable.
- key (Any | EMPTY): Optional key function spec; if provided (not `EMPTY`), uniqueness is determined by `key(item)` instead of `item`.
**Behavior**:
- Initialize an empty `set` named `seen`.
- If `key is EMPTY`:
- For each `item` in `seq` (in iteration order):
- If `item` is not in `seen`:
- Add `item` to `seen`.
- Yield `item`.
- Otherwise, skip it.
- Else (a key is supplied):
- Convert `key` to a callable using `make_func(key)`.
- For each `item` in `seq`:
- Compute `k = key(item)`.
- If `k` is not in `seen`:
- Add `k` to `seen`.
- Yield `item` (note: yield the original item, not the key).
- Otherwise, skip it.
- Uniqueness tracking uses a Python `set`, so the compared values (`item` when no key, or `k` when keyed) must be hashable; otherwise a `TypeError` will be raised when checking/adding.
- The function is lazy: it consumes `seq` only as the returned generator is advanced.
**Returns**:
- Iterator[Any]: A generator yielding the first occurrence of each distinct item/key in order of appearance.

---

## Function: split

```python
def split(pred, seq)
```

**split**: Lazily partition an iterable into two iterators: items that satisfy a predicate and items that do not, without eagerly consuming the whole input.
**Signature**: def split(pred, seq)
**Parameters**:
- pred (Any): Predicate spec converted to a callable via `make_pred`.
- seq (Iterable[Any]): Input iterable to be partitioned.
**Behavior**:
- Convert `pred` to a callable predicate using `make_pred(pred)`.
- Create two internal queues: `yes` and `no`, both `collections.deque()`.
- Create a lazy internal generator `splitter` that iterates through `seq` and, for each `item`:
- If `pred(item)` is truthy, append `item` to `yes`.
- Else, append `item` to `no`.
- The generator yields a value each time solely to allow advancing it with `next()`; the yielded value is not used.
- Define an inner generator function `_split(q)` (documented separately) that:
- Yields any already-queued items from deque `q`.
- If `q` is empty, advances `splitter` by one step to classify one more input item into either `yes` or `no`.
- Repeats until `splitter` is exhausted, then terminates.
- Return a pair of iterators: `_split(yes)` and `_split(no)`.
- Laziness and interaction:
- Advancing either returned iterator may consume additional items from `seq` (via `splitter`) to find items for its own queue.
- Items are buffered in the opposite queue when they belong to the other side; those buffered items remain until the corresponding iterator is advanced.
- If one side is never consumed, its buffered items may accumulate in memory.
**Returns**:
- tuple[Iterator[Any], Iterator[Any]]: `(passed_iter, failed_iter)` where `passed_iter` yields items with `pred(item)` truthy and `failed_iter` yields the rest, both in original order.

---

## Function: _split

```python
def _split(q)
```

**_split**: Internal generator used by `split` to drain a specific queue while incrementally advancing the shared splitter over the source iterable.
**Signature**: def _split(q)
**Parameters**:
- q (collections.deque): The deque to drain (either the `yes` or `no` queue created in `split`).
**Behavior**:
- Run an infinite loop:
- While `q` is non-empty:
- Pop and yield items from the left (`popleft`) until `q` becomes empty.
- When `q` is empty:
- Attempt to advance the shared `splitter` generator by calling `next(splitter)`.
- If advancing succeeds, exactly one new source item is classified and appended to either `yes` or `no`; then loop continues, which may now allow yielding from `q` if the classified item went into this queue.
- If advancing raises `StopIteration`, terminate the generator (return), meaning no more source items exist and the queue is empty.
- This generator relies on closures over `splitter` (and indirectly over the `yes`/`no` deques) created in `split`; it is not a standalone utility.
**Returns**:
- Iterator[Any]: A generator yielding items drained from `q` as they become available until the source is exhausted.

---

## Function: lsplit

```python
def lsplit(pred, seq)
```

**lsplit**: Eagerly partition an iterable into two lists: items that satisfy a predicate and items that do not.
**Signature**: def lsplit(pred, seq)
**Parameters**:
- pred (Any): Predicate spec converted to a callable via `make_pred`.
- seq (Iterable[Any]): Input iterable to be partitioned.
**Behavior**:
- Convert `pred` to a callable predicate using `make_pred(pred)`.
- Initialize two empty Python lists: `yes` and `no`.
- Iterate through `seq` in order:
- If `pred(item)` is truthy, append `item` to `yes`.
- Otherwise, append `item` to `no`.
- After consuming all of `seq`, return the two lists.
**Returns**:
- tuple[list[Any], list[Any]]: `(passed_list, failed_list)` preserving original order within each list.

---

## Function: split_at

```python
def split_at(n, seq)
```

**split_at**: Lazily split an iterable into two iterators at a given position, producing the first `n` items and the remaining tail.
**Signature**: def split_at(n, seq)
**Parameters**:
- n (int): Split index; the first iterator yields up to `n` items from the start.
- seq (Iterable[Any]): Input iterable.
**Behavior**:
- Duplicate the input iterable into two linked iterators using `itertools.tee(seq)`, producing `a` and `b`.
- Return a pair of `itertools.islice` views:
- The first is `islice(a, n)`, yielding the first `n` items from `a`.
- The second is `islice(b, n, None)`, skipping the first `n` items from `b` and yielding the rest.
- Both outputs are lazy; consumption of either side may cause `tee` to buffer items internally to keep the two iterators consistent.
- If `n` is 0, the first iterator yields nothing and the second yields all items.
- If `n` is greater than the number of items, the first yields all items and the second yields nothing.
**Returns**:
- tuple[Iterator[Any], Iterator[Any]]: `(head_iter, tail_iter)` where `head_iter` yields the first `n` items and `tail_iter` yields the remainder.

---

## Function: lsplit_at

```python
def lsplit_at(n, seq)
```

**lsplit_at**: Eagerly split an iterable into two lists at a given position.
**Signature**: def lsplit_at(n, seq)
**Parameters**:
- n (int): Split index; the first list contains up to `n` items.
- seq (Iterable[Any]): Input iterable.
**Behavior**:
- Call `split_at(n, seq)` to obtain `(a, b)` iterators for the head and tail.
- Convert `a` to a list to form the head list.
- Convert `b` to a list to form the tail list.
- Return the pair of lists.
**Returns**:
- tuple[list[Any], list[Any]]: `(head_list, tail_list)` where `head_list` contains the first `n` items (or fewer if input is shorter) and `tail_list` contains the remaining items.

---

## Function: split_by

```python
def split_by(pred, seq)
```

**split_by**: Lazily splits an input iterable into a prefix of items that satisfy a predicate and the remaining suffix starting at the first failure.
**Signature**: def split_by(pred, seq)
**Parameters**:
- pred (<any>): Predicate spec accepted by takewhile(); if called in two-argument mode it is converted via make_pred, and if used in one-argument mode of takewhile/dropwhile it is treated as the sequence (not applicable here because split_by always passes two args).
- seq (<iterable>): Source iterable to split; will be duplicated internally so both outputs can be iterated independently.
**Behavior**:
- Create two independent iterators over the same underlying input by calling itertools.tee(seq), producing a and b.
- Return a pair of iterators:
- - The first iterator yields items from a while the predicate holds, using takewhile(pred, a).
- - The second iterator yields items from b starting from the first item for which the predicate does not hold, using dropwhile(pred, b).
- Predicate handling is delegated to takewhile/dropwhile:
- - Because split_by passes both pred and an iterator, takewhile/dropwhile will convert pred using make_pred(pred) before applying it.
- The split is lazy:
- - No items are consumed until one of the returned iterators is advanced.
- - Advancing either iterator may cause tee’s shared buffer to grow if the other iterator lags behind.
- Edge cases:
- - If seq is empty, both returned iterators are empty.
- - If the first item fails pred, the first iterator is empty and the second yields the entire sequence.
- - If all items satisfy pred, the first yields all items and the second is empty.
**Returns**:
- (iterator, iterator): A 2-tuple (prefix_iter, suffix_iter) as described above.
**Notes**:
- The two returned iterators are coupled through tee buffering; consuming one far ahead of the other can increase memory usage.

---

## Function: lsplit_by

```python
def lsplit_by(pred, seq)
```

**lsplit_by**: Eagerly splits an input iterable into two lists: the leading run of items satisfying a predicate and the remaining items.
**Signature**: def lsplit_by(pred, seq)
**Parameters**:
- pred (<any>): Predicate spec passed to split_by (and ultimately to takewhile/dropwhile), converted via make_pred when applied.
- seq (<iterable>): Source iterable to split.
**Behavior**:
- Call split_by(pred, seq) to obtain two iterators (a, b): the satisfying prefix and the remaining suffix.
- Convert each iterator to a list by calling list(a) and list(b).
- Return the two lists as a tuple.
- This fully consumes the underlying sequence.
- Edge cases mirror split_by:
- - Empty input yields ([], []).
- - If the first item fails pred, returns ([], list(seq)).
- - If all items satisfy pred, returns (list(seq), []).
**Returns**:
- (list, list): A 2-tuple (prefix_list, suffix_list).

---

## Function: group_by

```python
def group_by(f, seq)
```

**group_by**: Groups items from a sequence into a mapping from a computed key to the list of items producing that key.
**Signature**: def group_by(f, seq)
**Parameters**:
- f (<any>): Key function spec; converted to a callable via make_func(f) and applied as f(item) to compute the grouping key.
- seq (<iterable>): Items to group.
**Behavior**:
- Convert f into a callable using make_func(f).
- Create result as collections.defaultdict(list).
- Iterate through seq in order:
- - For each item, compute key = f(item).
- - Append the original item to result[key].
- Preserve encounter order within each group because items are appended as they are seen.
- If seq is empty, result is an empty defaultdict(list).
**Returns**:
- collections.defaultdict[list]: A defaultdict mapping each computed key to a list of items with that key.
**Notes**:
- The returned object is specifically a defaultdict with list as the default factory (not a plain dict).

---

## Function: group_by_keys

```python
def group_by_keys(get_keys, seq)
```

**group_by_keys**: Groups items under multiple keys per item, producing a mapping from each key to the list of items that declared that key.
**Signature**: def group_by_keys(get_keys, seq)
**Parameters**:
- get_keys (<any>): Function spec converted via make_func; called as get_keys(item) and must return an iterable of keys for that item.
- seq (<iterable>): Items to group.
**Behavior**:
- Convert get_keys into a callable using make_func(get_keys).
- Create result as collections.defaultdict(list).
- Iterate through seq in order:
- - For each item, iterate over keys produced by get_keys(item).
- - For each key k, append the original item to result[k].
- Items may appear multiple times in the overall mapping if get_keys(item) yields multiple keys; they are appended once per yielded key.
- If get_keys(item) yields no keys, that item contributes nothing.
- If seq is empty, result is an empty defaultdict(list).
**Returns**:
- collections.defaultdict[list]: A defaultdict mapping each key to a list of items associated with that key.
**Notes**:
- The returned object is specifically a defaultdict with list as the default factory.

---

## Function: group_values

```python
def group_values(seq)
```

**group_values**: Converts a sequence of (key, value) pairs into a mapping from each key to the list of values associated with it.
**Signature**: def group_values(seq)
**Parameters**:
- seq (<iterable>): Iterable of 2-tuples (key, value); each element must be unpackable into exactly two components.
**Behavior**:
- Create result as collections.defaultdict(list).
- Iterate through seq:
- - Unpack each element into (key, value).
- - Append value to result[key].
- Preserve encounter order of values per key.
- If seq is empty, result is an empty defaultdict(list).
**Returns**:
- collections.defaultdict[list]: A defaultdict mapping each key to a list of collected values.
**Notes**:
- Input elements must be pairs; unpacking errors propagate.

---

## Function: count_by

```python
def count_by(f, seq)
```

**seqs module public API (export expectations)**: The module must export (define at top-level) the following public functions with the exact names listed. Aliases (e.g., `cat`, `lcat`) are not substitutes unless the required name itself exists and behaves as specified.
- concat
- lzip
- count_by

**concat**: Lazily concatenates multiple input iterables into a single iterator (sequence concatenation).
**Signature**: def concat(*seqs) -> collections.abc.Iterator
**Parameters**:
- seqs (collections.abc.Iterable, varargs): Zero or more iterables to be concatenated in the order provided.
**Behavior**:
- Accept any number of positional arguments; each argument must be iterable.
- Return a lazy iterator that yields items from the first iterable until it is exhausted, then continues with the next iterable, and so on.
- Do not materialize the inputs into a list/tuple as part of concatenation (concatenation is streaming/lazy).
- If no iterables are provided, return an iterator that yields no items.
- Do not modify the input iterables.
- The returned iterator must preserve standard iteration semantics of the inputs (including propagating any exceptions raised during iteration).
**Returns**:
- collections.abc.Iterator: An iterator producing all elements from each input iterable in order (equivalent in behavior to `itertools.chain(*seqs)`).

**lzip**: Eagerly zips multiple iterables and returns the zipped result as a list.
**Signature**: def lzip(*seqs) -> list[tuple]
**Parameters**:
- seqs (collections.abc.Iterable, varargs): Zero or more iterables whose elements will be grouped by position.
**Behavior**:
- Accept any number of positional arguments; each argument must be iterable.
- Perform standard zip semantics across the provided iterables:
- - Items are grouped by index/position into tuples.
- - The number of output tuples equals the length of the shortest input iterable (truncation to the shortest).
- - Iteration proceeds left-to-right across the zipped iterables; any exceptions raised by iterating an input must propagate.
- Eagerly materialize and return the complete zipped result as a list (not a generator/iterator).
- If no iterables are provided, return an empty list.
- Do not modify the input iterables.
**Returns**:
- list[tuple]: A list of tuples, each tuple containing one element from each input iterable at the same position (equivalent in behavior to `list(zip(*seqs))`).

**count_by**: Counts how many items in a sequence map to each key produced by a function.
**Signature**: def count_by(f, seq) -> collections.defaultdict
**Parameters**:
- f (typing.Any): Key function spec; converted to a callable via make_func(f) and applied as f(item).
- seq (collections.abc.Iterable): Items to count.
**Behavior**:
- Convert f into a callable using make_func(f).
- Create result as collections.defaultdict(int).
- Iterate through seq:
- - Compute key = f(item).
- - Increment result[key] by 1.
- If seq is empty, result is an empty defaultdict(int).
- Do not modify seq; only consume it via iteration.
- Propagate any exceptions raised by iterating seq or by applying f to an item.
**Returns**:
- collections.defaultdict[typing.Any, int]: A defaultdict mapping each computed key to its occurrence count, with int as the default factory.
**Notes**:
- The returned object is specifically a defaultdict with int as the default factory.

---

## Function: count_reps

```python
def count_reps(seq)
```

**count_reps**: Counts occurrences of each distinct item in a sequence.
**Signature**: def count_reps(seq)
**Parameters**:
- seq (<iterable>): Items to count; items must be usable as dictionary keys (hashable) for counting.
**Behavior**:
- Create result as collections.defaultdict(int).
- Iterate through seq:
- - For each item, increment result[item] by 1.
- If seq is empty, result is an empty defaultdict(int).
**Returns**:
- collections.defaultdict[int]: A defaultdict mapping each item to its occurrence count.
**Notes**:
- Items must be hashable; unhashable items will raise a TypeError when used as dict keys.

---

## Function: _cut_seq

```python
def _cut_seq(drop_tail, n, step, seq)
```

**_cut_seq**: Produces successive slices from a sliceable sequence, yielding windows of length n advanced by step, optionally dropping an incomplete tail.
**Signature**: def _cut_seq(drop_tail, n, step, seq)
**Parameters**:
- drop_tail (bool): If True, do not yield any final slice shorter than n; if False, include remaining tail slices shorter than n according to the same stepping.
- n (int): Window length used in slicing seq[i:i+n].
- step (int): Step between window starts (range increment).
- seq (collections.abc.Sequence): A sequence supporting len() and slicing.
**Behavior**:
- Compute limit:
- - If drop_tail is True: limit = len(seq) - n + 1.
- - If drop_tail is False: limit = len(seq).
- Return a generator expression that iterates i over range(0, limit, step) and yields seq[i:i+n] for each i.
- Consequences:
- - With drop_tail True, starts are limited so that i+n does not exceed len(seq), so all yielded slices have length exactly n (unless n <= 0, in which case Python slicing semantics apply).
- - With drop_tail False, starts may extend into the tail; seq[i:i+n] may be shorter than n near the end.
- If limit is <= 0, range(0, limit, step) is empty and nothing is yielded.
**Returns**:
- iterator: An iterator yielding subsequences produced by slicing.
**Notes**:
- This function assumes seq is a Sequence; it does not attempt to iterate non-sliceable iterables.

---

## Function: _cut_iter

```python
def _cut_iter(drop_tail, n, step, seq)
```

**_cut_iter**: Produces successive windows from a general iterable using a rolling buffer, optionally yielding a final incomplete tail.
**Signature**: def _cut_iter(drop_tail, n, step, seq)
**Parameters**:
- drop_tail (bool): If True, do not yield any final window shorter than n; if False, yield remaining tail windows shorter than n after the main loop.
- n (int): Target window size.
- step (int): Number of items to advance between yielded windows.
- seq (<iterable>): Source iterable (may be an iterator); will be consumed.
**Behavior**:
- Create an iterator it = iter(seq).
- Initialize a list buffer pool = take(n, it), where take returns a list of up to n items from it.
- Enter an infinite loop:
- - If len(pool) < n, break (not enough items for a full window).
- - Yield the current pool list (length exactly n).
- - Advance the window by step:
- - - Remove the first step items from pool via pool = pool[step:] (this creates a new list).
- - - Extend pool in-place with up to step new items from the iterator: pool.extend(islice(it, step)).
- After the loop ends (i.e., fewer than n items remain in pool):
- - If drop_tail is False, yield remaining tail chunks derived from the current pool by delegating to _cut_seq(drop_tail, n, step, pool) and yielding each produced slice.
- - If drop_tail is True, do nothing further (tail is ignored).
- Tail behavior when drop_tail is False:
- - Because _cut_seq is called with drop_tail=False and seq=pool (a list), it yields slices pool[i:i+n] for i in range(0, len(pool), step), which may include one or more shorter-than-n slices depending on len(pool) and step.
**Returns**:
- iterator: An iterator yielding lists representing windows/chunks.
**Notes**:
- Yielded windows from the main loop are lists of length n; tail yields (when enabled) are list slices that may be shorter.
- The function consumes the input iterable progressively and cannot be restarted.

---

## Function: _cut

```python
def _cut(drop_tail, n, step, seq=EMPTY)
```

**_cut**: Dispatches to an efficient cutting implementation for sequences vs general iterables, with an optional 2-argument calling convention.
**Signature**: def _cut(drop_tail, n, step, seq=EMPTY)
**Parameters**:
- drop_tail (bool): Passed through to _cut_seq/_cut_iter; controls whether to drop or include incomplete tail windows.
- n (int): Window size.
- step (int | <iterable>): If seq is provided, this is the step size; if seq is omitted (seq is EMPTY), this parameter is treated as the sequence and step is set to n.
- seq (<iterable> | EMPTY): Source sequence/iterable; if omitted, the function uses the 2-argument convention described above.
**Behavior**:
- Support two calling conventions:
- - 3-argument form: _cut(drop_tail, n, step, seq) where step is an int and seq is the iterable.
- - 2-argument form: _cut(drop_tail, n, seq) achieved by passing seq as the third positional argument and leaving seq at its default EMPTY; in this case:
- - - Detect seq is EMPTY.
- - - Rebind (step, seq) = (n, step), so step becomes n and seq becomes the originally provided third argument.
- Choose implementation based on whether seq is a sliceable Sequence:
- - If isinstance(seq, collections.abc.Sequence) is True, return _cut_seq(drop_tail, n, step, seq).
- - Otherwise, return _cut_iter(drop_tail, n, step, seq).
- No iteration is performed immediately; both branches return iterators.
**Returns**:
- iterator: An iterator yielding windows/chunks as produced by _cut_seq (slices) or _cut_iter (lists).
**Notes**:
- The Sequence branch yields slices of the original sequence type (via seq[i:i+n]); the iterator branch yields Python lists.

---

## Function: partition

```python
def partition(n, step, seq=EMPTY)
```

**partition**: Lazily yields fixed-length windows from a sequence/iterable, advancing by a given step and dropping any final incomplete window.

**Signature**: def partition(n: int, step: int | collections.abc.Iterable, seq: object = EMPTY) -> collections.abc.Iterator[object]

**Parameters**:
- n (int): Window length (number of items per partition). Must be a positive integer (> 0).
- step (int | collections.abc.Iterable): In 3-argument form, the advance between consecutive window start positions, measured in items. In 2-argument form (`seq` omitted/`EMPTY`), this argument is treated as `seq` and `step` defaults to `n`.
- seq (object): Input sequence/iterable. If omitted (equals `EMPTY`), the function uses the 2-argument calling convention described above.

**Behavior**:
- Calling conventions:
- 3-argument form: `partition(n, step, seq)` where `step` is an integer stride and `seq` is the input.
- 2-argument form: `partition(n, seq)` implemented by calling `partition(n, step, seq=EMPTY)`; in this case the function sets `seq = step` and `step = n`.
- Parameter validation:
- `n` must be > 0; otherwise raise `ValueError`.
- `step` must be an integer and must be > 0; otherwise raise `ValueError`.
- Conceptual semantics (applies to all input types):
- Each yielded window corresponds to `n` consecutive items from the input.
- Window start positions advance by exactly `step` items from the previous window’s start.
- If `step < n`, consecutive windows overlap.
- If `step == n`, consecutive windows are adjacent (no overlap, no gaps).
- If `step > n`, windows are separated by gaps: after yielding a window, exactly `step - n` items between the end of that window and the start of the next window are skipped/discarded from the input stream.
- Any final suffix that cannot form a full window of length `n` is ignored (not yielded).
- Branch for `collections.abc.Sequence` inputs (supports `len()` and slicing):
- Compute `limit = len(seq) - n + 1`.
- If `limit <= 0`, yield nothing.
- Otherwise, for `i` in `range(0, limit, step)`, yield `seq[i:i+n]`.
- This guarantees every yielded part has length exactly `n`; any tail shorter than `n` is ignored.
- Branch for non-`Sequence` iterables (generic iterables/iterators):
- Create an iterator `it = iter(seq)`.
- Read the first `n` items from `it` into a list `pool`.
- If fewer than `n` items are available, yield nothing and stop.
- While `len(pool) == n`:
- Yield the current `pool` list (a snapshot of the current window).
- Advance the window start by exactly `step` items relative to the previous start:
- If `step <= n`:
- Drop the first `step` items from `pool` (keeping the remaining `n - step` items as overlap).
- Pull up to `step` new items from `it` and append them to `pool` to attempt to restore length `n`.
- If `step > n`:
- Discard the entire current `pool` (all `n` items have already been yielded as the window).
- Additionally skip/discard exactly `step - n` further items from `it` (these form the gap between windows).
- Then pull the next `n` items from `it` into a fresh `pool` to form the next window.
- Stop when a full window cannot be formed (i.e., after refilling, `len(pool) < n`); do not yield any remaining partial tail.
- Side effects and consumption:
- No mutation of the input sequence is performed.
- For generic iterables, the input iterator is consumed as windows are produced, including any skipped items implied by `step > n`.

**Returns**:
- An iterator/generator yielding partitions:
- For `Sequence` inputs: slices of the original sequence.
- For non-`Sequence` iterables: lists.
- Every yielded partition has length exactly `n`.

---

## Function: lpartition

```python
def lpartition(n, step, seq=EMPTY)
```

**lpartition**: Eager (list) version of `partition`, returning all fixed-length partitions at once.
**Signature**: def lpartition(n, step, seq=EMPTY)
**Parameters**:
- n (int): Window length (number of items per partition).
- step (int | collections.abc.Iterable): Step between windows, or the sequence itself in the 2-argument calling convention.
- seq (object): Input sequence/iterable, or `EMPTY` to use the 2-argument calling convention.
**Behavior**:
- Calls `partition(n, step, seq)` with the same two calling conventions as `partition`.
- Fully consumes the iterator returned by `partition` and collects each yielded partition into a Python `list`.
- For `Sequence` inputs, elements of the result are slices of the original sequence; for non-`Sequence` iterables, elements are lists produced by the underlying iterator-based algorithm.
**Returns**:
- list: A list containing every partition produced by `partition` (possibly empty).

---

## Function: chunks

```python
def chunks(n, step, seq=EMPTY)
```

**chunks**: Lazily yields windows from a sequence/iterable, advancing by a given step, and includes the final incomplete tail as shorter chunks.
**Signature**: def chunks(n, step, seq=EMPTY)
**Parameters**:
- n (int): Nominal chunk length; full chunks have length `n` when possible.
- step (int | collections.abc.Iterable): If `seq` is provided, this is the advance between consecutive chunks; if `seq` is omitted (left as `EMPTY`), this argument is treated as `seq` and `step` defaults to `n`.
- seq (object): Input sequence/iterable; if omitted (equals `EMPTY`), the function uses the 2-argument calling convention described above.
**Behavior**:
- Supports two calling conventions:
- 3-argument form: `chunks(n, step, seq)`.
- 2-argument form: `chunks(n, seq)` implemented by passing `seq=EMPTY`; in this case set `seq = step` and `step = n`.
- If `seq` is a `collections.abc.Sequence`:
- Compute `limit = len(seq)`.
- Yield `seq[i:i+n]` for `i` in `range(0, limit, step)`.
- The last yielded slice may be shorter than `n` if the sequence ends.
- Otherwise treat `seq` as a generic iterable:
- Create an iterator `it = iter(seq)`.
- Read the first `n` items into a list `pool`.
- While `len(pool) == n`:
- Yield `pool`.
- Advance by `step` items by dropping `step` items from the front (`pool = pool[step:]`) and extending with up to `step` new items from `it`.
- When `len(pool) < n`, do not stop immediately; instead, if `pool` is non-empty, yield the remaining tail as one or more chunks using the same slicing logic as for sequences:
- Yield `pool[i:i+n]` for `i` in `range(0, len(pool), step)`.
- This can yield a final chunk shorter than `n`.
- Consumes the input iterator as chunks are produced; does not mutate the input.
**Returns**:
- An iterator/generator yielding chunks (slices for `Sequence` inputs; lists for non-`Sequence` iterables), where the final chunk(s) may be shorter than `n`.

---

## Function: lchunks

```python
def lchunks(n, step, seq=EMPTY)
```

**lchunks**: Eager (list) version of `chunks`, returning all chunks (including final incomplete ones) at once.
**Signature**: def lchunks(n, step, seq=EMPTY)
**Parameters**:
- n (int): Nominal chunk length.
- step (int | collections.abc.Iterable): Step between chunks, or the sequence itself in the 2-argument calling convention.
- seq (object): Input sequence/iterable, or `EMPTY` to use the 2-argument calling convention.
**Behavior**:
- Calls `chunks(n, step, seq)` with the same two calling conventions as `chunks`.
- Fully consumes the iterator returned by `chunks` and collects each yielded chunk into a Python `list`.
- For `Sequence` inputs, elements of the result are slices of the original sequence; for non-`Sequence` iterables, elements are lists produced by the underlying iterator-based algorithm.
**Returns**:
- list: A list containing every chunk produced by `chunks` (possibly empty).

---

## Function: partition_by

```python
def partition_by(f, seq)
```

**partition_by**: Lazily groups consecutive items into runs where a key function produces the same value, yielding an iterator for each run.
**Signature**: def partition_by(f, seq)
**Parameters**:
- f (object): Key function spec; converted to a callable via `make_func(f)` and applied to each item to compute its grouping key.
- seq (collections.abc.Iterable): Input iterable to partition into consecutive groups.
**Behavior**:
- Convert `f` to a callable using `make_func`.
- Iterate over `itertools.groupby(seq, f)`, which groups only consecutive items with equal keys.
- For each `(key, items_iter)` produced by `groupby`, ignore `key` and `yield items_iter`.
- Each yielded `items_iter` is itself an iterator over the items in that group; it is tied to the underlying `groupby` iterator, so consuming groups must proceed in order.
**Returns**:
- iterator: Yields one iterator per consecutive group (run) of items sharing the same `f(item)` value.

---

## Function: lpartition_by

```python
def lpartition_by(f, seq)
```

**lpartition_by**: Eager version of `partition_by` that returns each consecutive group as a concrete list.
**Signature**: def lpartition_by(f, seq)
**Parameters**:
- f (object): Key function spec; passed through to `partition_by` (which converts it via `make_func`).
- seq (collections.abc.Iterable): Input iterable to partition.
**Behavior**:
- Calls `partition_by(f, seq)` to obtain an iterator of group iterators.
- Converts each group iterator into a list.
- Collects all group lists into a single list and returns it.
**Returns**:
- list[list]: A list where each element is a list of consecutive items from `seq` that shared the same key value.

---

## Function: with_prev

```python
def with_prev(seq, fill=None)
```

**with_prev**: Pairs each item with the item that preceded it in the input, using a fill value for the first item.
**Signature**: def with_prev(seq, fill=None)
**Parameters**:
- seq (collections.abc.Iterable): Input iterable.
- fill (object | None): Value to use as the “previous” element for the first item.
**Behavior**:
- Create two independent iterators over `seq` using `itertools.tee(seq)`, named `a` and `b`.
- Construct an iterator of previous-values as `chain([fill], b)`, i.e. yield `fill` first, then all items from `b`.
- Return `zip(a, chain([fill], b))`.
- The resulting iterator yields tuples `(item, prev)` where:
- `item` comes from `a` (the original sequence in order).
- `prev` is `fill` for the first item, then the immediately preceding item from the original sequence.
- Consuming the result consumes the underlying tees; no eager buffering beyond what `tee` requires.
**Returns**:
- iterator: An iterator of 2-tuples `(item, prev)` aligned to the input order.

---

## Function: with_next

```python
def with_next(seq, fill=None)
```

**with_next**: Pairs each item with the item that follows it in the input, using a fill value for the last item.
**Signature**: def with_next(seq, fill=None)
**Parameters**:
- seq (collections.abc.Iterable): Input iterable.
- fill (object | None): Value to use as the “next” element for the last item.
**Behavior**:
- Create two independent iterators over `seq` using `itertools.tee(seq)`, named `a` and `b`.
- Advance `b` by one element via `next(b, None)` to align it as the “next” stream; the discarded value is ignored.
- Construct an iterator of next-values as `chain(b, [fill])`, i.e. all remaining items from `b` followed by `fill`.
- Return `zip(a, chain(b, [fill]))`.
- The resulting iterator yields tuples `(item, nxt)` where:
- `item` comes from `a`.
- `nxt` is the immediately following item from the original sequence, or `fill` for the last item.
- Consuming the result consumes the underlying tees; no eager buffering beyond what `tee` requires.
**Returns**:
- iterator: An iterator of 2-tuples `(item, next)` aligned to the input order.

---

## Function: pairwise

```python
def pairwise(seq)
```

**pairwise**: Lazily yields overlapping pairs of neighboring items from the input.
**Signature**: def pairwise(seq)
**Parameters**:
- seq (collections.abc.Iterable): Input iterable.
**Behavior**:
- Create two independent iterators over `seq` using `itertools.tee(seq)`, named `a` and `b`.
- Advance `b` by one element via `next(b, None)` so that `b` is offset by one relative to `a`.
- Return `zip(a, b)`.
- The resulting iterator yields `(x0, x1), (x1, x2), ...` until either iterator is exhausted; for inputs with fewer than 2 items, yields nothing.
**Returns**:
- iterator: An iterator of 2-tuples of adjacent items.

---

## Function: _reductions

```python
def _reductions(f, seq, acc)
```

**_reductions**: Internal generator that yields successive accumulator states produced by reducing a sequence with a binary function starting from an explicit initial accumulator.
**Signature**: def _reductions(f, seq, acc)
**Parameters**:
- f (collections.abc.Callable): Binary function `f(accumulator, x) -> new_accumulator`.
- seq (collections.abc.Iterable): Input iterable of values to fold into the accumulator.
- acc (object): Initial accumulator value.
**Behavior**:
- Initialize a local variable `last` to `acc`.
- Iterate through `seq` in order:
- Update `last = f(last, x)` for the current element `x`.
- Yield the updated `last`.
- Does not yield the initial `acc` itself; only yields after applying `f` to at least one element.
- Consumes `seq` as it yields results; no other side effects.
**Returns**:
- iterator: Yields each intermediate reduced value after processing each element of `seq`.

---

## Function: reductions

```python
def reductions(f, seq, acc=EMPTY)
```

**reductions**: Lazily yields the running (intermediate) reduction results of a sequence under a binary function.
**Signature**: def reductions(f, seq, acc=EMPTY)
**Parameters**:
- f (<callable>): Binary function of the form f(accumulator, item) -> new_accumulator; used to combine values.
- seq (<iterable>): Input iterable whose items are reduced from left to right.
- acc (<any>): Optional initial accumulator value; if omitted (i.e., equals EMPTY sentinel), the first element of seq is used as the initial value (via itertools.accumulate semantics).
**Behavior**:
- If acc is the EMPTY sentinel (meaning no explicit initial accumulator was provided):
- Use itertools.accumulate to compute running reductions over seq.
- Special-case optimization: if f is exactly operator.add (identity comparison), call accumulate(seq) with no function argument (uses the default addition behavior).
- Otherwise call accumulate(seq, f).
- The resulting iterator yields one value per input element, starting with the first element of seq (as the initial accumulated value), then f(prev, next_item), etc.
- If seq is empty, the iterator yields nothing.
- If acc is not EMPTY (explicit initial accumulator provided):
- Iterate through seq left-to-right.
- Maintain a variable last initialized to acc.
- For each element x in seq:
- Update last = f(last, x).
- Yield last.
- If seq is empty, yield nothing (the initial acc itself is not yielded).
- No eager consumption of seq beyond what the returned iterator requires.
**Returns**:
- (<iterator>): An iterator yielding the intermediate reduction results as described above.
**Notes**:
- When acc is omitted, behavior matches itertools.accumulate: the first yielded value is the first element of seq (not f(acc, first)).
- When acc is provided, the first yielded value is f(acc, first_element).

---

## Function: lreductions

```python
def lreductions(f, seq, acc=EMPTY)
```

**lreductions**: Eagerly computes and returns a list of the running (intermediate) reduction results of a sequence under a binary function.
**Signature**: def lreductions(f, seq, acc=EMPTY)
**Parameters**:
- f (<callable>): Binary function of the form f(accumulator, item) -> new_accumulator.
- seq (<iterable>): Input iterable whose items are reduced from left to right.
- acc (<any>): Optional initial accumulator value; if omitted (EMPTY), reductions start from the first element of seq per itertools.accumulate semantics.
**Behavior**:
- Call reductions(f, seq, acc) to obtain an iterator of intermediate reduction results.
- Materialize that iterator into a list using list(...).
- This fully consumes seq.
**Returns**:
- (<list>): All values that reductions(f, seq, acc) would yield, in the same order.
**Notes**:
- If seq is empty, returns an empty list regardless of acc.

---

## Function: sums

```python
def sums(seq, acc=EMPTY)
```

**sums**: Lazily yields running (partial) sums of a sequence.
**Signature**: def sums(seq, acc=EMPTY)
**Parameters**:
- seq (<iterable>): Input iterable of addable values.
- acc (<any>): Optional initial accumulator value; if omitted (EMPTY), summation starts from the first element of seq (itertools.accumulate default behavior).
**Behavior**:
- Delegate to reductions(operator.add, seq, acc).
- Therefore:
- If acc is EMPTY, yields the same sequence as itertools.accumulate(seq) (first yield is first element of seq).
- If acc is provided, first yield is acc + first_element (via operator.add), and subsequent yields add each next element to the running total.
- If seq is empty, yields nothing.
**Returns**:
- (<iterator>): An iterator yielding partial sums.
**Notes**:
- This is a thin wrapper over reductions with f fixed to operator.add.

---

## Function: lsums

```python
def lsums(seq, acc=EMPTY)
```

**lsums**: Eagerly computes and returns a list of running (partial) sums of a sequence.
**Signature**: def lsums(seq, acc=EMPTY)
**Parameters**:
- seq (<iterable>): Input iterable of addable values.
- acc (<any>): Optional initial accumulator value; if omitted (EMPTY), summation starts from the first element of seq.
**Behavior**:
- Delegate to lreductions(operator.add, seq, acc), thereby computing the same values as sums(seq, acc) but materialized into a list.
- Fully consumes seq.
**Returns**:
- (<list>): All partial sums in order; empty list if seq is empty.
**Notes**:
- This is a thin wrapper over lreductions with f fixed to operator.add.
