from __future__ import annotations

import builtins
import collections
import itertools
import operator
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any

_map = builtins.map
_filter = builtins.filter

EMPTY = object()


def _lmap(f, *seqs):
    return list(map(f, *seqs))


def _lfilter(f, seq):
    return list(filter(f, seq))


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


def make_func(f):
    if callable(f):
        return f
    if f is None:
        def _identity(x, *args):
            return x
        return _identity
    if isinstance(f, str):
        def _accessor(x, *args):
            try:
                return x[f]  # type: ignore[index]
            except TypeError:
                return getattr(x, f)
        return _accessor
    if isinstance(f, int):
        def _indexer(x, *args):
            return x[f]  # type: ignore[index]
        return _indexer
    if isinstance(f, (list, tuple)):
        def _project(x, *args):
            return tuple(x[k] for k in f)  # type: ignore[index]
        return _project
    if isinstance(f, dict):
        if "path" in f:
            path = f["path"]
        elif "keys" in f:
            path = f["keys"]
        elif "steps" in f:
            path = f["steps"]
        else:
            path = list(f.values())
        if not isinstance(path, (list, tuple)):
            raise TypeError("dict function specification must contain a list/tuple path")
        def _path(x, *args):
            cur = x
            for step in path:
                if isinstance(step, str):
                    try:
                        cur = cur[step]  # type: ignore[index]
                    except TypeError:
                        cur = getattr(cur, step)
                else:
                    cur = cur[step]  # type: ignore[index]
            return cur
        return _path
    raise TypeError("Unsupported function specification")


def make_pred(pred):
    if pred is None:
        return bool
    if callable(pred):
        return pred
    if isinstance(pred, (str, int, list, tuple, dict)):
        func = make_func(pred)
        def _p(x):
            return bool(func(x))
        return _p
    if isinstance(pred, set):
        def _in(x):
            return x in pred
        return _in
    def _eq(x):
        return x == pred
    return _eq


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
    return _filter(bool, map(f, seq))


def lkeep(f, seq=EMPTY):
    return list(keep(f, seq))


def without(seq, *items):
    for value in seq:
        if value not in items:
            yield value


def lwithout(seq, *items):
    return list(without(seq, *items))


def concat(*seqs):
    return itertools.chain(*seqs)


def lconcat(*seqs):
    return list(itertools.chain(*seqs))


def cat(seqs):
    return itertools.chain.from_iterable(seqs)


def lcat(seqs):
    return list(itertools.chain.from_iterable(seqs))


def lzip(*seqs):
    return list(zip(*seqs))


def is_seqcont(x):
    if isinstance(x, (str, bytes, bytearray)):
        return False
    if isinstance(x, Mapping):
        return False
    return isinstance(x, Iterable)


def flatten(seq, follow=is_seqcont):
    active: set[int] = set()

    def _gen(s):
        for item in s:
            if follow(item):
                oid = id(item)
                if oid in active:
                    yield item
                    continue
                active.add(oid)
                try:
                    for sub in _gen(item):
                        yield sub
                finally:
                    active.remove(oid)
            else:
                yield item

    return _gen(seq)


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
    limit = (len(seq) - n + 1) if drop_tail else len(seq)
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
        if limit <= 0:
            return iter(())
        return (seq[i:i + n] for i in range(0, limit, step))

    def _gen():
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

    return _gen()


def lpartition(n, step, seq=EMPTY):
    return list(partition(n, step, seq))


def chunks(n, step, seq=EMPTY):
    if seq is EMPTY:
        seq = step
        step = n
    return _cut(False, n, step, seq)


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
