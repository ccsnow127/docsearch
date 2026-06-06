from __future__ import annotations

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

_map = map
_filter = filter


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
    return next(iter(seq), None)


def second(seq):
    return first(rest(seq))


def nth(n, seq):
    try:
        return seq[n]
    except IndexError:
        return None
    except TypeError:
        return next(itertools.islice(seq, n, None), None)


def last(seq):
    try:
        return seq[-1]
    except IndexError:
        return None
    except TypeError:
        item = None
        for item in seq:
            pass
        return item


def rest(seq):
    return drop(1, seq)


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


def _access_str(x, name: str):
    try:
        return x[name]
    except (TypeError, LookupError):
        return getattr(x, name)


def _make_path_func(steps):
    def _path(x, *args):
        cur = x
        for step in steps:
            if isinstance(step, str):
                cur = _access_str(cur, step)
            elif isinstance(step, int):
                cur = cur[step]
            else:
                raise TypeError("Unsupported path step type")
        return cur

    return _path


def make_func(f):
    if callable(f):
        return f
    if f is None:
        def _id(x, *args):
            return x
        return _id
    if isinstance(f, str):
        def _getter(x, *args):
            return _access_str(x, f)
        return _getter
    if isinstance(f, int):
        def _indexer(x, *args):
            return x[f]
        return _indexer
    if isinstance(f, (list, tuple)):
        def _proj(x, *args):
            return tuple(x[k] for k in f)
        return _proj
    if isinstance(f, dict):
        if "path" in f:
            steps = f["path"]
        elif "steps" in f:
            steps = f["steps"]
        else:
            steps = list(f.values()) if len(f) == 1 else None
            if steps is None:
                raise TypeError("Unsupported dict function specification")
            steps = steps[0]
        if not isinstance(steps, (list, tuple)):
            raise TypeError("Path steps must be a list/tuple")
        return _make_path_func(list(steps))
    raise TypeError("Unsupported function specification")


def make_pred(pred):
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


def concat(*seqs) -> Iterator:
    return itertools.chain(*seqs)


def lzip(*seqs):
    return list(zip(*seqs))


def lcat(seqs):
    return list(itertools.chain.from_iterable(seqs))


def cat(seqs):
    return itertools.chain.from_iterable(seqs)


def is_seqcont(x):
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
                    for y in _flat(item):
                        yield y
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
    return rest(interleave(itertools.repeat(sep), seq))


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
    seen = set()
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
    pred_f = make_pred(pred)
    yes = collections.deque()
    no = collections.deque()

    def splitter():
        for item in seq:
            if pred_f(item):
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
    pred_f = make_pred(pred)
    yes = []
    no = []
    for item in seq:
        if pred_f(item):
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
    func = make_func(f)
    res = collections.defaultdict(list)
    for item in seq:
        res[func(item)].append(item)
    return res


def group_by_keys(get_keys, seq):
    func = make_func(get_keys)
    res = collections.defaultdict(list)
    for item in seq:
        for k in func(item):
            res[k].append(item)
    return res


def group_values(seq):
    res = collections.defaultdict(list)
    for k, v in seq:
        res[k].append(v)
    return res


def count_by(f, seq):
    func = make_func(f)
    res = collections.defaultdict(int)
    for item in seq:
        res[func(item)] += 1
    return res


def count_reps(seq):
    res = collections.defaultdict(int)
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
        for part in _cut_seq(False, n, step, pool):
            yield part


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
        raise ValueError
    if not isinstance(step, int) or step <= 0:
        raise ValueError

    if isinstance(seq, Sequence):
        limit = len(seq) - n + 1
        for i in range(0, max(limit, 0), step):
            part = seq[i:i + n]
            if len(part) == n:
                yield part
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
        for part in _cut_seq(False, n, step, pool):
            yield part


def lchunks(n, step, seq=EMPTY):
    return list(chunks(n, step, seq))


def partition_by(f, seq):
    func = make_func(f)
    for _, items in itertools.groupby(seq, func):
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
    last = acc
    for x in seq:
        last = f(last, x)
        yield last


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
