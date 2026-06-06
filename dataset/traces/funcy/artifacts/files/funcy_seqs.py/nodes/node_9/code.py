from __future__ import annotations

import builtins
import collections
import itertools
import operator
from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Callable


class _EmptySentinel:
    __slots__ = ()

    def __repr__(self) -> str:
        return "EMPTY"


EMPTY = _EmptySentinel()

_map = builtins.map
_filter = builtins.filter


def make_func(f: Any) -> Callable:
    if callable(f):
        return f
    if isinstance(f, str):
        return operator.attrgetter(f)
    if isinstance(f, (tuple, list)) and len(f) == 2:
        op, arg = f
        if op == "attr":
            return operator.attrgetter(arg)
        if op == "item":
            return operator.itemgetter(arg)
    raise TypeError("Cannot convert to function")


def make_pred(pred: Any) -> Callable[[Any], bool]:
    if pred is None:
        return lambda x: True
    if callable(pred):
        return pred
    if isinstance(pred, str):
        g = operator.attrgetter(pred)
        return lambda x: bool(g(x))
    if isinstance(pred, (tuple, list)) and len(pred) == 2:
        op, arg = pred
        if op == "attr":
            g = operator.attrgetter(arg)
            return lambda x: bool(g(x))
        if op == "item":
            g = operator.itemgetter(arg)
            return lambda x: bool(g(x))
    raise TypeError("Cannot convert to predicate")


def is_seqcont(x: Any) -> bool:
    return isinstance(x, (list, tuple))


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


def lmap(f, *seqs):
    return list(_map(make_func(f), *seqs))


def lfilter(pred, seq):
    return list(_filter(make_pred(pred), seq))


def map(f, *seqs):
    return _map(make_func(f), *seqs)


def filter(pred, seq):
    return _filter(make_pred(pred), seq)


def remove(pred, seq):
    return itertools.filterfalse(make_pred(pred), seq)


def lremove(pred, seq):
    return list(remove(pred, seq))


def keep(f, seq=EMPTY):
    if seq is EMPTY:
        return filter(bool, f)
    return filter(bool, map(f, seq))


def lkeep(f, seq=EMPTY):
    return list(keep(f, seq))


def without(seq, *items):
    for value in seq:
        if value not in items:
            yield value


def lwithout(seq, *items):
    return list(without(seq, *items))


def concat(*seqs) -> Iterator:
    return itertools.chain(*seqs)


def lconcat(*seqs: object) -> list:
    return list(itertools.chain(*seqs))


def lcat(seqs):
    return list(itertools.chain.from_iterable(seqs))


def cat(seqs):
    return itertools.chain.from_iterable(seqs)


def flatten(seq, follow=is_seqcont):
    for item in seq:
        if follow(item):
            yield from flatten(item, follow)
        else:
            yield item


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
    pred_f = make_pred(pred)
    yes: collections.deque = collections.deque()
    no: collections.deque = collections.deque()

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
    yes: list[Any] = []
    no: list[Any] = []
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
    f = make_func(f)
    res: collections.defaultdict = collections.defaultdict(list)
    for item in seq:
        res[f(item)].append(item)
    return res


def group_by_keys(get_keys, seq):
    get_keys = make_func(get_keys)
    res: collections.defaultdict = collections.defaultdict(list)
    for item in seq:
        for k in get_keys(item):
            res[k].append(item)
    return res


def group_values(seq):
    res: collections.defaultdict = collections.defaultdict(list)
    for k, v in seq:
        res[k].append(v)
    return res


def count_by(f, seq) -> collections.defaultdict:
    f = make_func(f)
    res: collections.defaultdict = collections.defaultdict(int)
    for item in seq:
        res[f(item)] += 1
    return res


def count_reps(seq):
    res: collections.defaultdict = collections.defaultdict(int)
    for item in seq:
        res[item] += 1
    return res


def _cut_seq(drop_tail, n, step, seq):
    if drop_tail:
        limit = len(seq) - n + 1
    else:
        limit = len(seq)
    return (seq[i : i + n] for i in range(0, limit, step))


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
        seq, step = step, n
    if n <= 0:
        raise ValueError
    if not isinstance(step, int) or step <= 0:
        raise ValueError

    if isinstance(seq, Sequence):
        limit = len(seq) - n + 1
        if limit <= 0:
            return iter(())
        return (seq[i : i + n] for i in range(0, limit, step))

    def gen():
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

    return gen()


def lpartition(n, step, seq=EMPTY):
    return list(partition(n, step, seq))


def chunks(n, step, seq=EMPTY):
    return _cut(False, n, step, seq)


def lchunks(n, step, seq=EMPTY):
    return list(chunks(n, step, seq))


def partition_by(f, seq):
    f = make_func(f)
    for _, items in itertools.groupby(seq, f):
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


def lzip(*seqs) -> list[tuple]:
    return list(zip(*seqs))
