import operator
import pytest
import importlib.util
import pathlib
import sys

# Load the local seqs.py as part of a synthetic package so its relative imports work.
# This ensures we test THIS repository's seqs.py (module under test), not any installed funcy.
_pkg_root = pathlib.Path(__file__).resolve().parent
_seqs_path = _pkg_root / "seqs.py"

# Create a synthetic package name and ensure repo_sources is on sys.path for dependencies.
sys.path.insert(0, str(_pkg_root / "repo_sources"))

_pkg_name = "_local_funcy"
_mod_name = f"{_pkg_name}.seqs"

if _pkg_name not in sys.modules:
    pkg = importlib.util.module_from_spec(importlib.machinery.ModuleSpec(_pkg_name, None))
    pkg.__path__ = [str(_pkg_root / "repo_sources" / "funcy")]
    sys.modules[_pkg_name] = pkg

spec = importlib.util.spec_from_file_location(_mod_name, _seqs_path)
seqs_mod = importlib.util.module_from_spec(spec)
seqs_mod.__package__ = _pkg_name
sys.modules[_mod_name] = seqs_mod
assert spec.loader is not None
spec.loader.exec_module(seqs_mod)

# Import names from the loaded module under test
repeatedly = seqs_mod.repeatedly
iterate = seqs_mod.iterate

take = seqs_mod.take
drop = seqs_mod.drop
first = seqs_mod.first
second = seqs_mod.second
nth = seqs_mod.nth
last = seqs_mod.last
rest = seqs_mod.rest
butlast = seqs_mod.butlast
ilen = seqs_mod.ilen

lmap = seqs_mod.lmap
lfilter = seqs_mod.lfilter
emap = seqs_mod.map
efilter = seqs_mod.filter

remove = seqs_mod.remove
lremove = seqs_mod.lremove
keep = seqs_mod.keep
lkeep = seqs_mod.lkeep
without = seqs_mod.without
lwithout = seqs_mod.lwithout

lconcat = seqs_mod.lconcat
concat = seqs_mod.concat
lcat = seqs_mod.lcat
cat = seqs_mod.cat
flatten = seqs_mod.flatten
lflatten = seqs_mod.lflatten
mapcat = seqs_mod.mapcat
lmapcat = seqs_mod.lmapcat

interleave = seqs_mod.interleave
interpose = seqs_mod.interpose
distinct = seqs_mod.distinct
ldistinct = seqs_mod.ldistinct

split = seqs_mod.split
lsplit = seqs_mod.lsplit
split_at = seqs_mod.split_at
lsplit_at = seqs_mod.lsplit_at
split_by = seqs_mod.split_by
lsplit_by = seqs_mod.lsplit_by

group_by = seqs_mod.group_by
group_by_keys = seqs_mod.group_by_keys
group_values = seqs_mod.group_values
count_by = seqs_mod.count_by
count_reps = seqs_mod.count_reps

partition = seqs_mod.partition
lpartition = seqs_mod.lpartition
chunks = seqs_mod.chunks
lchunks = seqs_mod.lchunks
partition_by = seqs_mod.partition_by
lpartition_by = seqs_mod.lpartition_by

with_prev = seqs_mod.with_prev
with_next = seqs_mod.with_next
pairwise = seqs_mod.pairwise
lzip = seqs_mod.lzip

reductions = seqs_mod.reductions
lreductions = seqs_mod.lreductions
sums = seqs_mod.sums
lsums = seqs_mod.lsums


def test_repeatedly_repeatedly_n_and_infinite_prefix():
    c = {"n": 0}

    def f():
        c["n"] += 1
        return c["n"]

    assert list(repeatedly(f, 3)) == [1, 2, 3]

    # infinite version: just take a prefix
    c["n"] = 0
    assert take(4, repeatedly(f)) == [1, 2, 3, 4]


def test_iterate_iterate_generates_sequence():
    it = iterate(lambda x: x * 2, 1)
    assert take(5, it) == [1, 2, 4, 8, 16]


def test_take_take_and_drop_drop_basic():
    assert take(3, [1, 2, 3, 4]) == [1, 2, 3]
    assert list(drop(2, [1, 2, 3, 4])) == [3, 4]


def test_first_first_second_second_empty_and_short():
    assert first([]) is None
    assert first([10, 20]) == 10
    assert second([10]) is None
    assert second([10, 20, 30]) == 20


def test_nth_nth_sequence_and_iterator_paths():
    assert nth(1, [5, 6, 7]) == 6
    assert nth(10, [1, 2, 3]) is None

    # iterator path (TypeError for __getitem__)
    it = iter([9, 8, 7])
    assert nth(2, it) == 7
    assert nth(5, iter([1, 2])) is None


def test_last_last_sequence_and_iterator_paths():
    assert last([1, 2, 3]) == 3
    assert last([]) is None

    # iterator path
    assert last(iter([4, 5, 6])) == 6
    assert last(iter([])) is None


def test_rest_rest_and_butlast_butlast_and_ilen_ilen():
    assert list(rest([1, 2, 3])) == [2, 3]
    assert list(butlast([1, 2, 3])) == [1, 2]
    assert list(butlast([])) == []

    # ilen consumes
    it = iter(range(7))
    assert ilen(it) == 7
    assert list(it) == []


def test_lmap_lfilter_map_filter_make_func_and_make_pred():
    # string mapper: attribute access
    class Obj:
        def __init__(self, v):
            self.v = v

    objs = [Obj(1), Obj(2)]
    assert lmap("v", objs) == [1, 2]

    # dict mapper: lookup
    assert lmap({"a": 1, "b": 2}, ["b", "a"]) == [2, 1]

    # slice predicate: membership in range
    assert lfilter(slice(2, 5), [1, 2, 3, 4, 5]) == [2, 3, 4]

    # extended map/filter return iterators
    assert list(emap("v", objs)) == [1, 2]
    assert list(efilter(slice(2, 5), [1, 2, 3, 4, 5])) == [2, 3, 4]


def test_remove_remove_lremove_lremove_and_keep_keep_variants():
    assert list(remove(lambda x: x % 2 == 0, [1, 2, 3, 4])) == [1, 3]
    assert lremove(lambda x: x < 0, [1, -1, 2, -2]) == [1, 2]

    # keep one-arg: filters truthy values
    assert list(keep([0, 1, "", "x", None, 2])) == [1, "x", 2]
    assert lkeep([0, 1, 2]) == [1, 2]

    # keep two-arg: map then keep truthy
    assert list(keep(lambda x: x if x % 2 else 0, [1, 2, 3, 4])) == [1, 3]


def test_without_without_lwithout_lwithout_order_preserved():
    assert list(without([1, 2, 3, 2, 4], 2, 4)) == [1, 3]
    assert lwithout(["a", "b", "a"], "a") == ["b"]


def test_lconcat_concat_lcat_cat_and_flatten_flatten_mapcat_mapcat():
    assert lconcat([1, 2], [3]) == [1, 2, 3]
    assert list(concat([1], [2, 3])) == [1, 2, 3]

    assert lcat([[1, 2], [3], []]) == [1, 2, 3]
    assert list(cat([["a"], ["b", "c"]])) == ["a", "b", "c"]

    nested = [1, [2, (3, 4)], "xy"]
    # default follow should not dive into strings (depends on is_seqcont)
    flat = list(flatten(nested))
    assert "xy" in flat
    assert flat[:4] == [1, 2, 3, 4]

    # custom follow: dive into strings too
    flat2 = lflatten(["ab", ["c"]], follow=lambda x: isinstance(x, (list, tuple, str)))
    assert flat2 == ["a", "b", "c"]

    assert list(mapcat(lambda x: [x, x + 10], [1, 2])) == [1, 11, 2, 12]
    assert lmapcat(lambda x: [x], [1, 2, 3]) == [1, 2, 3]


def test_interleave_interleave_and_interpose_interpose():
    assert list(interleave([1, 2], ["a", "b"])) == [1, "a", 2, "b"]
    assert list(interpose(0, [1, 2, 3])) == [1, 0, 2, 0, 3]


def test_distinct_distinct_and_ldistinct_ldistinct_keyed():
    assert list(distinct([1, 2, 1, 3, 2])) == [1, 2, 3]
    assert ldistinct(["a", "A", "b", "B"], key=str.lower) == ["a", "b"]


def test_split_split_lazy_and_lsplit_lsplit_eager():
    passed, failed = split(lambda x: x % 2 == 0, [1, 2, 3, 4, 5])
    # consume in interleaved order to exercise internal buffering
    assert next(passed) == 2
    assert next(failed) == 1
    assert list(passed) == [4]
    assert list(failed) == [3, 5]

    yes, no = lsplit(lambda x: x > 0, [-1, 0, 1])
    assert yes == [1]
    assert no == [-1, 0]


def test_split_at_split_at_and_lsplit_at_lsplit_at():
    a, b = split_at(2, [1, 2, 3, 4])
    assert list(a) == [1, 2]
    assert list(b) == [3, 4]

    a2, b2 = lsplit_at(3, [1, 2, 3, 4])
    assert a2 == [1, 2, 3]
    assert b2 == [4]


def test_split_by_split_by_and_lsplit_by_lsplit_by_one_arg_predicate():
    a, b = split_by(lambda x: x < 3, [1, 2, 3, 1])
    assert list(a) == [1, 2]
    assert list(b) == [3, 1]

    a2, b2 = lsplit_by([1, 2, 0, 3])  # one-arg version uses truthiness
    assert a2 == [1, 2]
    assert b2 == [0, 3]


def test_group_by_group_by_and_group_by_keys_group_by_keys_and_group_values_group_values():
    gb = group_by(lambda x: x % 2, [1, 2, 3, 4])
    assert gb[0] == [2, 4]
    assert gb[1] == [1, 3]

    gbk = group_by_keys(lambda s: set(s), ["ab", "bc"])
    assert gbk["b"] == ["ab", "bc"]
    assert gbk["a"] == ["ab"]

    gv = group_values([("k", 1), ("k", 2), ("j", 3)])
    assert gv["k"] == [1, 2]
    assert gv["j"] == [3]


def test_count_by_count_by_and_count_reps_count_reps():
    cb = count_by(lambda x: x % 2, [1, 2, 3, 4, 6])
    assert cb[0] == 3
    assert cb[1] == 2

    cr = count_reps(["a", "b", "a"])
    assert cr["a"] == 2
    assert cr["b"] == 1


def test_partition_partition_and_lpartition_lpartition_sequence_and_iter_tail_drop():
    assert list(partition(2, 2, [1, 2, 3, 4, 5])) == [[1, 2], [3, 4]]
    assert lpartition(3, 1, [1, 2, 3, 4]) == [[1, 2, 3], [2, 3, 4]]

    # iterator path
    it = (x for x in [1, 2, 3, 4, 5])
    assert list(partition(2, 3, it)) == [[1, 2], [4, 5]]


def test_chunks_chunks_and_lchunks_lchunks_include_tail():
    assert list(chunks(2, 2, [1, 2, 3, 4, 5])) == [[1, 2], [3, 4], [5]]

    it = iter([1, 2, 3, 4, 5])
    assert lchunks(3, 2, it) == [[1, 2, 3], [3, 4, 5], [5]]


def test_partition_by_partition_by_and_lpartition_by_lpartition_by():
    parts = list(partition_by(lambda x: x % 2, [1, 3, 2, 4, 5]))
    assert [list(p) for p in parts] == [[1, 3], [2, 4], [5]]

    assert lpartition_by(lambda x: x, [1, 1, 2, 2, 2, 3]) == [[1, 1], [2, 2, 2], [3]]


def test_with_prev_with_prev_and_with_next_with_next_and_pairwise_pairwise():
    assert list(with_prev([1, 2, 3], fill=0)) == [(1, 0), (2, 1), (3, 2)]
    assert list(with_next([1, 2, 3], fill=0)) == [(1, 2), (2, 3), (3, 0)]
    assert list(pairwise([1, 2, 3])) == [(1, 2), (2, 3)]


def test_lzip_lzip_strict_and_non_strict():
    assert lzip([1, 2], ["a", "b"]) == [(1, "a"), (2, "b")]

    # strict mismatch should raise ValueError
    with pytest.raises(ValueError):
        lzip([1, 2, 3], ["a", "b"], strict=True)


def test_reductions_reductions_and_lreductions_lreductions_and_sums_sums_lsums_lsums():
    assert list(reductions(operator.mul, [1, 2, 3], 1)) == [1, 2, 6]

    # acc EMPTY: uses itertools.accumulate; for add should behave like partial sums
    assert list(reductions(operator.add, [1, 2, 3])) == [1, 3, 6]

    assert lreductions(operator.sub, [10, 1, 2], 0) == [-10, -11, -13]

    assert list(sums([1, 2, 3])) == [1, 3, 6]
    assert lsums([1, 2, 3], 10) == [11, 13, 16]
