from __future__ import annotations

import builtins
import collections
import itertools
import operator
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any


class _EmptySentinel:
    __slots__ = ()

    def __repr__(self) -> str:
        return "EMPTY"


EMPTY = _EmptySentinel()

_map = builtins.map
_filter = builtins.filter


def _lmap(f, *seqs):
    return list(_map(f, *seqs))


def _lfilter(f, seq):
    return list(_filter(f, seq))


def repeatedly(f, n=EMPTY):
    if n is EMPTY:
        _repeat = itertools.repeat(None)
    else:
        _repeat = itertools.repeat(None, n)
    return (f() for _ in _repeat)


def iterate(f, x):
    while True:
        yield x
        x = f(x)


def take(n, seq):
    return list(itertools.islice(seq, n))


def drop(n, seq):
    return itertools.islice(seq, n, None)


def first(seq):
    it = iter(seq)
    return next(it, None)


def rest(seq):
    return drop(1, seq)


def second(seq):
    return first(rest(seq))


def nth(n, seq):
    try:
        return seq[n]  # type: ignore[index]
    except IndexError:
        return None
    except TypeError:
        return next(itertools.islice(seq, n, None), None)


def last(seq):
    try:
        return seq[-1]  # type: ignore[index]
    except IndexError:
        return None
    except TypeError:
        item = None
        for item in seq:
            pass
        return item


def butlast(seq):
    it = iter(seq)
    try:
        prev = next(it)
    except StopIteration:
        return
        yield  # pragma: no cover
    for item in it:
        yield prev
        prev = item


def ilen(seq):
    counter = itertools.count()
    collections.deque(zip(seq, counter), maxlen=0)
    return next(counter)


def _string_accessor(name: str) -> Callable[..., Any]:
    def _acc(x, *args):
        try:
            return x[name]
        except TypeError:
            return getattr(x, name)

    return _acc


def make_func(f: Any) -> Callable[..., Any]:
    if callable(f):
        return f

    if f is None:
        def _identity(x, *args):
            return x
        return _identity

    if isinstance(f, str):
        return _string_accessor(f)

    if isinstance(f, int):
        def _idx(x, *args):
            return x[f]
        return _idx

    if isinstance(f, (list, tuple)):
        keys = tuple(f)

        def _proj(x, *args):
            return tuple(x[k] for k in keys)
        return _proj

    if isinstance(f, dict):
        path_keys = [k for k in ("path", "steps", "get", "in") if k in f]
        comp_keys = [k for k in ("call", "compose", "juxt") if k in f]

        if path_keys and comp_keys:
            raise TypeError("Ambiguous dict function specification (path and composition keys present)")
        if len(path_keys) > 1:
            raise TypeError("Ambiguous dict path specification (multiple path keys present)")

        if path_keys:
            pk = path_keys[0]
            steps_val = f[pk]
            if isinstance(steps_val, (list, tuple)):
                steps = list(steps_val)
            else:
                steps = [steps_val]

            compiled_steps: list[Any] = []
            for step in steps:
                if isinstance(step, (str, int)) or callable(step) or isinstance(step, (list, tuple)):
                    compiled_steps.append(step)
                elif isinstance(step, dict):
                    compiled_steps.append(make_func(step))
                else:
                    raise TypeError(f"Unsupported path step type: {type(step).__name__}")

            def _path(x, *args):
                cur = x
                for step in compiled_steps:
                    if isinstance(step, str):
                        try:
                            cur = cur[step]
                        except TypeError:
                            cur = getattr(cur, step)
                    elif isinstance(step, int):
                        cur = cur[step]
                    elif isinstance(step, (list, tuple)):
                        cur = tuple(cur[k] for k in step)
                    elif callable(step):
                        cur = step(cur)
                    else:
                        raise TypeError(f"Unsupported compiled path step type: {type(step).__name__}")
                return cur

            return _path

        if comp_keys:
            if len(comp_keys) > 1:
                raise TypeError("Ambiguous dict composition specification (multiple composition keys present)")
            ck = comp_keys[0]

            if ck == "compose":
                specs = f[ck]
                if not isinstance(specs, (list, tuple)) or len(specs) < 1:
                    raise TypeError('"compose" value must be a non-empty list/tuple of function specifications')
                funcs = [make_func(s) for s in specs]

                def _composed(*args):
                    res = funcs[-1](*args)
                    for fn in reversed(funcs[:-1]):
                        res = fn(res)
                    return res

                return _composed

            if ck == "juxt":
                specs = f[ck]
                if not isinstance(specs, (list, tuple)) or len(specs) < 1:
                    raise TypeError('"juxt" value must be a non-empty list/tuple of function specifications')
                funcs = [make_func(s) for s in specs]

                def _juxt(*args):
                    return tuple(fn(*args) for fn in funcs)

                return _juxt

            if ck == "call":
                spec = f[ck]
                if not isinstance(spec, dict):
                    raise TypeError('"call" value must be a dict')
                if "fn" not in spec:
                    raise TypeError('"call" dict must contain "fn"')
                fn_spec = spec["fn"]
                fn_func = make_func(fn_spec)

                args_specs = spec.get("args", ())
                if args_specs is None:
                    args_specs = ()
                if not isinstance(args_specs, (list, tuple)):
                    raise TypeError('"call.args" must be a list/tuple if provided')
                arg_funcs = [make_func(s) for s in args_specs]

                kwargs_specs = spec.get("kwargs", {})
                if kwargs_specs is None:
                    kwargs_specs = {}
                if not isinstance(kwargs_specs, dict):
                    raise TypeError('"call.kwargs" must be a dict if provided')
                for k in kwargs_specs.keys():
                    if not isinstance(k, str):
                        raise TypeError('"call.kwargs" keys must be strings')
                kw_funcs = {k: make_func(v) for k, v in kwargs_specs.items()}

                def _call(*args):
                    h = fn_func(*args)
                    pos_args = [g(*args) for g in arg_funcs]
                    kw_args = {k: g(*args) for k, g in kw_funcs.items()}
                    return h(*pos_args, **kw_args)

                return _call

            raise TypeError("Unsupported dict composition specification")

        raise TypeError("Unsupported dict function specification")

    raise TypeError(f"Unsupported function specification: {type(f).__name__}")


def make_pred(pred: Any) -> Callable[[Any], bool]:
    if pred is None:
        return bool
    if callable(pred):
        return pred
    func = make_func(pred)

    def _p(x):
        return bool(func(x))

    return _p


def lmap(f, *seqs):
    func = make_func(f)
    return list(_map(func, *seqs))


def lfilter(pred, seq):
    p = make_pred(pred)
    return list(_filter(p, seq))


def map(f, *seqs):
    func = make_func(f)
    return _map(func, *seqs)


def filter(pred, seq):
    p = make_pred(pred)
    return _filter(p, seq)


def remove(pred, seq):
    p = make_pred(pred)
    return itertools.filterfalse(p, seq)


def lremove(pred, seq):
    return list(remove(pred, seq))


def keep(f, seq=EMPTY):
    if seq is EMPTY:
        return _filter(bool, f)
    mapped = map(f, seq)
    return _filter(bool, mapped)


def lkeep(f, seq=EMPTY):
    return list(keep(f, seq))


def without(seq, *items):
    for value in seq:
        if value not in items:
            yield value


def lwithout(seq, *items):
    return list(without(seq, *items))


def lconcat(*seqs):
    return list(itertools.chain(*seqs))


def cat(seqs):
    return itertools.chain.from_iterable(seqs)


def lcat(seqs):
    return list(itertools.chain.from_iterable(seqs))


def is_seqcont(x: Any) -> bool:
    if isinstance(x, (str, bytes, bytearray)):
        return False
    if isinstance(x, Mapping):
        return False
    return isinstance(x, Iterable)


def flatten(seq, follow=is_seqcont):
    active: set[int] = set()

    def _flat(s):
        for item in s:
            if follow(item):
                oid = id(item)
                if oid in active:
                    yield item
                    continue
                active.add(oid)
                try:
                    yield from _flat(item)
                finally:
                    active.remove(oid)
            else:
                yield item

    return _flat(seq)


def lflatten(seq, follow=is_seqcont):
    return list(flatten(seq, follow))


def mapcat(f, *seqs):
    return cat(map(f, *seqs))


def lmapcat(f, *seqs):
    return lcat(map(f, *seqs))


def interleave(*seqs):
    return cat(zip(*seqs))


def interpose(sep, seq):
    return drop(1, interleave(itertools.repeat(sep), seq))


def takewhile(pred, seq=EMPTY):
    if seq is EMPTY:
        seq = pred
        predicate = bool
    else:
        predicate = make_pred(pred)
    return itertools.takewhile(predicate, seq)


def dropwhile(pred, seq=EMPTY):
    if seq is EMPTY:
        seq = pred
        predicate = bool
    else:
        predicate = make_pred(pred)
    return itertools.dropwhile(predicate, seq)


def distinct(seq, key=EMPTY):
    seen: set[Any] = set()
    if key is EMPTY:
        for item in seq:
            if item not in seen:
                seen.add(item)
                yield item
    else:
        kf = make_func(key)
        for item in seq:
            k = kf(item)
            if k not in seen:
                seen.add(k)
                yield item


def ldistinct(seq, key=EMPTY):
    return list(distinct(seq, key))


def split(pred, seq):
    p = make_pred(pred)
    yes: collections.deque[Any] = collections.deque()
    no: collections.deque[Any] = collections.deque()

    def splitter():
        for item in seq:
            if p(item):
                yes.append(item)
            else:
                no.append(item)
            yield None

    _splitter = splitter()

    def _split(q):
        while True:
            while q:
                yield q.popleft()
            try:
                next(_splitter)
            except StopIteration:
                return

    return _split(yes), _split(no)


def lsplit(pred, seq):
    p = make_pred(pred)
    yes: list[Any] = []
    no: list[Any] = []
    for item in seq:
        if p(item):
            yes.append(item)
        else:
            no.append(item)
    return yes, no


def split_at(n, seq):
    a, b = itertools.tee(seq)
    return itertools.islice(a, n), itertools.islice(b, n, None)


def lsplit_at(n, seq):
    a, b = split_at(n, seq)
    return list(a), list(b)


def split_by(pred, seq):
    a, b = itertools.tee(seq)
    return takewhile(pred, a), dropwhile(pred, b)


def lsplit_by(pred, seq):
    a, b = split_by(pred, seq)
    return list(a), list(b)


def group_by(f, seq):
    fn = make_func(f)
    res: collections.defaultdict[Any, list[Any]] = collections.defaultdict(list)
    for item in seq:
        res[fn(item)].append(item)
    return res


def group_by_keys(get_keys, seq):
    fn = make_func(get_keys)
    res: collections.defaultdict[Any, list[Any]] = collections.defaultdict(list)
    for item in seq:
        for k in fn(item):
            res[k].append(item)
    return res


def group_values(seq):
    res: collections.defaultdict[Any, list[Any]] = collections.defaultdict(list)
    for k, v in seq:
        res[k].append(v)
    return res


def concat(*seqs) -> Iterator[Any]:
    return itertools.chain(*seqs)


def lzip(*seqs) -> list[tuple]:
    return list(zip(*seqs))


def count_by(f, seq):
    fn = make_func(f)
    res: collections.defaultdict[Any, int] = collections.defaultdict(int)
    for item in seq:
        res[fn(item)] += 1
    return res


def count_reps(seq):
    res: collections.defaultdict[Any, int] = collections.defaultdict(int)
    for item in seq:
        res[item] += 1
    return res


def _cut_seq(drop_tail, n, step, seq):
    if drop_tail:
        limit = len(seq) - n + 1
    else:
        limit = len(seq)
    return (seq[i:i + n] for i in range(0, limit, step))


def _cut_iter(drop_tail, n, step, seq):
    it = iter(seq)
    pool = take(n, it)
    while True:
        if len(pool) < n:
            break
        yield pool
        pool = pool[step:]
        pool.extend(itertools.islice(it, step))
    if not drop_tail:
        yield from _cut_seq(False, n, step, pool)


def _cut(drop_tail, n, step, seq=EMPTY):
    if seq is EMPTY:
        step, seq = n, step
    if isinstance(seq, Sequence):
        return _cut_seq(drop_tail, n, step, seq)
    return _cut_iter(drop_tail, n, step, seq)


def partition(n, step, seq=EMPTY):
    if seq is EMPTY:
        seq = step
        step = n
    if n <= 0:
        raise ValueError("n must be > 0")
    if not isinstance(step, int) or step <= 0:
        raise ValueError("step must be an int > 0")

    if isinstance(seq, Sequence):
        limit = len(seq) - n + 1
        for i in range(0, limit, step):
            yield seq[i:i + n]
        return

    it = iter(seq)
    pool = take(n, it)
    if len(pool) < n:
        return
    while len(pool) == n:
        yield pool
        if step <= n:
            pool = pool[step:]
            pool.extend(itertools.islice(it, step))
        else:
            collections.deque(itertools.islice(it, step - n), maxlen=0)
            pool = take(n, it)
            if len(pool) < n:
                return


def lpartition(n, step, seq=EMPTY):
    return list(partition(n, step, seq))


def chunks(n, step, seq=EMPTY):
    if seq is EMPTY:
        seq = step
        step = n

    if isinstance(seq, Sequence):
        limit = len(seq)
        for i in range(0, limit, step):
            yield seq[i:i + n]
        return

    it = iter(seq)
    pool = take(n, it)
    while len(pool) == n:
        yield pool
        pool = pool[step:]
        pool.extend(itertools.islice(it, step))
    if pool:
        yield from _cut_seq(False, n, step, pool)


def lchunks(n, step, seq=EMPTY):
    return list(chunks(n, step, seq))


def partition_by(f, seq):
    fn = make_func(f)
    for _, items in itertools.groupby(seq, fn):
        yield items


def lpartition_by(f, seq):
    return [list(g) for g in partition_by(f, seq)]


def with_prev(seq, fill=None):
    a, b = itertools.tee(seq)
    return zip(a, itertools.chain([fill], b))


def with_next(seq, fill=None):
    a, b = itertools.tee(seq)
    next(b, None)
    return zip(a, itertools.chain(b, [fill]))


def pairwise(seq):
    a, b = itertools.tee(seq)
    next(b, None)
    return zip(a, b)


def _reductions(f, seq, acc):
    last_val = acc
    for x in seq:
        last_val = f(last_val, x)
        yield last_val


def reductions(f, seq, acc=EMPTY):
    if acc is EMPTY:
        if f is operator.add:
            return itertools.accumulate(seq)
        return itertools.accumulate(seq, f)
    return _reductions(f, seq, acc)


def lreductions(f, seq, acc=EMPTY):
    return list(reductions(f, seq, acc))


def sums(seq, acc=EMPTY):
    return reductions(operator.add, seq, acc)


def lsums(seq, acc=EMPTY):
    return lreductions(operator.add, seq, acc)
