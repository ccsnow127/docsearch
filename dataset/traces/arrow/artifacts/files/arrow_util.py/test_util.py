import datetime
import math
import pytest

import util
from arrow import constants


def test_next_weekday_next_weekday_same_day_returns_start_when_matches():
    start = datetime.date(1970, 1, 1)  # Thursday
    result = util.next_weekday(start, 3)
    assert result == datetime.datetime(1970, 1, 1, 0, 0, 0)


def test_next_weekday_next_weekday_future_day_in_same_week():
    start = datetime.date(1970, 1, 1)  # Thursday
    result = util.next_weekday(start, 6)  # Sunday
    assert result == datetime.datetime(1970, 1, 4, 0, 0, 0)


def test_next_weekday_next_weekday_wraps_to_next_week():
    start = datetime.date(1970, 1, 1)  # Thursday
    result = util.next_weekday(start, 0)  # Monday
    assert result == datetime.datetime(1970, 1, 5, 0, 0, 0)


def test_next_weekday_next_weekday_invalid_weekday_raises():
    with pytest.raises(ValueError):
        util.next_weekday(datetime.date(2020, 1, 1), -1)
    with pytest.raises(ValueError):
        util.next_weekday(datetime.date(2020, 1, 1), 7)


def test_is_timestamp_is_timestamp_accepts_int_float_and_numeric_str():
    assert util.is_timestamp(0)
    assert util.is_timestamp(123.456)
    assert util.is_timestamp("42")
    assert util.is_timestamp("  42.5 ")


def test_is_timestamp_is_timestamp_rejects_bool_and_non_numeric():
    assert util.is_timestamp(True) is False
    assert util.is_timestamp(False) is False
    assert util.is_timestamp(object()) is False
    assert util.is_timestamp("not-a-number") is False


def test_validate_ordinal_validate_ordinal_type_errors_for_non_int_or_bool():
    with pytest.raises(TypeError):
        util.validate_ordinal(True)
    with pytest.raises(TypeError):
        util.validate_ordinal(1.0)
    with pytest.raises(TypeError):
        util.validate_ordinal("1")


def test_validate_ordinal_validate_ordinal_value_errors_out_of_range():
    with pytest.raises(ValueError):
        util.validate_ordinal(constants.MIN_ORDINAL - 1)
    with pytest.raises(ValueError):
        util.validate_ordinal(constants.MAX_ORDINAL + 1)


def test_validate_ordinal_validate_ordinal_accepts_min_and_max():
    util.validate_ordinal(constants.MIN_ORDINAL)
    util.validate_ordinal(constants.MAX_ORDINAL)


def test_normalize_timestamp_normalize_timestamp_no_change_when_within_seconds_range():
    ts = constants.MAX_TIMESTAMP - 1
    assert util.normalize_timestamp(ts) == ts


def test_normalize_timestamp_normalize_timestamp_divides_milliseconds():
    # pick a value just above MAX_TIMESTAMP but below MAX_TIMESTAMP_MS
    ts_ms = constants.MAX_TIMESTAMP + 1000
    assert ts_ms < constants.MAX_TIMESTAMP_MS
    normalized = util.normalize_timestamp(ts_ms)
    assert math.isclose(normalized, ts_ms / 1000)


def test_normalize_timestamp_normalize_timestamp_divides_microseconds():
    # pick a value between MAX_TIMESTAMP_MS and MAX_TIMESTAMP_US
    ts_us = constants.MAX_TIMESTAMP_MS + 1
    assert ts_us > constants.MAX_TIMESTAMP
    assert ts_us < constants.MAX_TIMESTAMP_US
    normalized = util.normalize_timestamp(ts_us)
    assert math.isclose(normalized, ts_us / 1_000_000)


def test_normalize_timestamp_normalize_timestamp_too_large_raises():
    with pytest.raises(ValueError):
        util.normalize_timestamp(constants.MAX_TIMESTAMP_US + 1)


def test_iso_to_gregorian_iso_to_gregorian_known_reference_date():
    # ISO year 1970 week 1 day 4 is 1970-01-01 (Thursday)
    assert util.iso_to_gregorian(1970, 1, 4) == datetime.date(1970, 1, 1)


def test_iso_to_gregorian_iso_to_gregorian_week_53_valid_and_computes():
    # 2015 has ISO week 53; day 7 is Sunday 2016-01-03
    assert util.iso_to_gregorian(2015, 53, 7) == datetime.date(2016, 1, 3)


def test_iso_to_gregorian_iso_to_gregorian_invalid_week_raises():
    with pytest.raises(ValueError):
        util.iso_to_gregorian(2020, 0, 1)
    with pytest.raises(ValueError):
        util.iso_to_gregorian(2020, 54, 1)


def test_iso_to_gregorian_iso_to_gregorian_invalid_day_raises():
    with pytest.raises(ValueError):
        util.iso_to_gregorian(2020, 1, 0)
    with pytest.raises(ValueError):
        util.iso_to_gregorian(2020, 1, 8)


def test_validate_bounds_validate_bounds_accepts_all_valid():
    for b in ("()", "(]", "[)", "[]"):
        util.validate_bounds(b)


def test_validate_bounds_validate_bounds_rejects_invalid():
    with pytest.raises(ValueError):
        util.validate_bounds("{}")
