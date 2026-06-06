import datetime
from typing import Any, Optional

from dateutil.rrule import WEEKLY, rrule

# Latest supported instant (domain cutoff) expressed as a concrete Unix-epoch seconds value.
# Chosen as 9999-12-31 23:59:59 UTC, which is 253402300799 seconds since 1970-01-01 00:00:00 UTC.
MAX_TIMESTAMP: float = 253402300799.0
MAX_TIMESTAMP_MS: float = MAX_TIMESTAMP * 1000
MAX_TIMESTAMP_US: float = MAX_TIMESTAMP * 1_000_000

# Gregorian ordinal bounds (datetime.date supports years 1..9999).
MIN_ORDINAL: int = 1
MAX_ORDINAL: int = 3652059


def next_weekday(start_date: Optional[datetime.date], weekday: int) -> datetime.datetime:
    if weekday < 0 or weekday > 6:
        raise ValueError("Weekday must be between 0 (Monday) and 6 (Sunday).")
    return rrule(freq=WEEKLY, dtstart=start_date, byweekday=weekday, count=1)[0]


def is_timestamp(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float, str)):
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def validate_ordinal(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Ordinal must be an integer (got type {type(value)}).")
    if not (MIN_ORDINAL <= value <= MAX_ORDINAL):
        raise ValueError(f"Ordinal {value} is out of range.")


def normalize_timestamp(timestamp: float) -> float:
    if timestamp <= MAX_TIMESTAMP:
        return float(timestamp)
    if MAX_TIMESTAMP < timestamp <= MAX_TIMESTAMP_MS:
        return float(timestamp) / 1000
    if MAX_TIMESTAMP_MS < timestamp <= MAX_TIMESTAMP_US:
        return float(timestamp) / 1_000_000
    raise ValueError(f"The specified timestamp {repr(timestamp)} is too large.")


def iso_to_gregorian(iso_year: int, iso_week: int, iso_day: int) -> datetime.date:
    if not (1 <= iso_week <= 53):
        raise ValueError("ISO Calendar week value must be between 1-53.")
    if not (1 <= iso_day <= 7):
        raise ValueError("ISO Calendar day value must be between 1-7")
    fourth_jan = datetime.date(iso_year, 1, 4)
    delta = datetime.timedelta(fourth_jan.isoweekday() - 1)
    year_start = fourth_jan - delta
    gregorian = year_start + datetime.timedelta(days=iso_day - 1, weeks=iso_week - 1)
    return gregorian


def validate_bounds(bounds: str) -> None:
    if bounds not in ("()", "(]", "[)", "[]"):
        raise ValueError("Invalid bounds. Please select between '()', '(]', '[)', or '[]'.")
