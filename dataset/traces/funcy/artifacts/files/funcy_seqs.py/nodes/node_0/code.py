from __future__ import annotations

import builtins
import collections
import itertools
import operator
from collections.abc import Callable, Iterable, Sequence

EMPTY = object()

_map = builtins.map
_filter = builtins.filter


def make_func(f):
    if callable(f):
        return f
    if isinstance(f, str):
        return operator.attrgetter(f)
    if isinstance(f, int):
        return operator.itemgetter(f)
    if isinstance(f, (tuple, list)):
        if len(f) == 0:
            return lambda x: x
        if len(f) == 1:
            return make_func(f[0])
        funcs = [make_func(x) for x in f]

        def _composed(x):
            for fn in funcs:
                x = fn(x)
            return x

        return _composed
    if isinstance(f, dict):
        return lambda x: f[x]
    return lambda _: f


def make_pred(pred):
    if pred is None:
        return bool
    if callable(pred):
        return pred
    if isinstance(pred, (set, frozenset, list, tuple, dict)):
        return lambda x: x in pred
    if isinstance(pred, str):
        getter = operator.attrgetter(pred)
        return lambda x: bool(getter(x))
    if isinstance(pred, int):
        getter = operator.itemgetter(pred)
        return lambda x: bool(getter(x))
    return lambda x: x == pred


def is_seqcont(x):
    if isinstance(x, (str, bytes, bytearray, memoryview)):
        return False
    return isinstance(x, Iterable)


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
    f = make_func(f)
    return list(_map(f, *seqs))


def lfilter(pred, seq):
    pred = make_pred(pred)
    return list(_filter(pred, seq))


def map(f, *seqs):
    f = make_func(f)
    return _map(f, *seqs)


def filter(pred, seq):
    pred = make_pred(pred)
    return _filter(pred, seq)


def lremove(pred, seq):
    return list(remove(pred, seq))


def remove(pred, seq):
    pred = make_pred(pred)
    return itertools.filterfalse(pred, seq)


def lkeep(f, seq=EMPTY):
    return list(keep(f, seq))


def keep(f, seq=EMPTY):
    if seq is EMPTY:
        return filter(bool, f)
    return filter(bool, map(f, seq))


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


def flatten(seq, follow=is_seqcont):
    for item in seq:
        if follow(item):
            yield from flatten(item, follow)
        else:
            yield item


def lflatten(seq, follow=is_seqcont):
    return list(flatten(seq, follow))


def lmapcat(f, *seqs):
    return lcat(map(f, *seqs))


def mapcat(f, *seqs):
    return cat(map(f, *seqs))


def interleave(*seqs):
    return cat(zip(*seqs))


def interpose(sep, seq):
    return drop(1, interleave(itertools.repeat(sep), seq))


def takewhile(pred, seq=EMPTY):
    if seq is EMPTY:
        seq = pred
        pred = bool
    else:
        pred = make_pred(pred)
    return itertools.takewhile(pred, seq)


def dropwhile(pred, seq=EMPTY):
    if seq is EMPTY:
        seq = pred
        pred = bool
    else:
        pred = make_pred(pred)
    return itertools.dropwhile(pred, seq)


def ldistinct(seq, key=EMPTY):
    return list(distinct(seq, key))


def distinct(seq, key=EMPTY):
    seen = set()
    if key is EMPTY:
        for item in seq:
            if item not in seen:
                seen.add(item)
                yield item
    else:
        keyf = make_func(key)
        for item in seq:
            k = keyf(item)
            if k not in seen:
                seen.add(k)
                yield item


def split(pred, seq):
    pred = make_pred(pred)
    yes = collections.deque()
    no = collections.deque()

    def splitter():
        for item in seq:
            if pred(item):
                yes.append(item)
            else:
                no.append(item)
            yield None

    splitter_gen = splitter()

    def _split(q):
        while True:
            while q:
                yield q.popleft()
            try:
                next(splitter_gen)
            except StopIteration:
                return

    return _split(yes), _split(no)


def lsplit(pred, seq):
    pred = make_pred(pred)
    yes = []
    no = []
    for item in seq:
        if pred(item):
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
    res = collections.defaultdict(list)
    for item in seq:
        res[f(item)].append(item)
    return res


def group_by_keys(get_keys, seq):
    get_keys = make_func(get_keys)
    res = collections.defaultdict(list)
    for item in seq:
        for k in get_keys(item):
            res[k].append(item)
    return res


def group_values(seq):
    res = collections.defaultdict(list)
    for k, v in seq:
        res[k].append(v)
    return res


def count_by(f, seq):
    f = make_func(f)
    res = collections.defaultdict(int)
    for item in seq:
        res[f(item)] += 1
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
    return _cut(True, n, step, seq)


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
