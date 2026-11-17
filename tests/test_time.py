"""Synthetic clock cases only; no exchange-calendar or provider claims."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from drift.time import BarInterval

ET = ZoneInfo("America/New_York")


def test_close_is_not_available_until_delivery() -> None:
    start = datetime(2026, 3, 9, 15, 29, tzinfo=ET)
    end = start + timedelta(minutes=1)
    available = end + timedelta(milliseconds=100)
    interval = BarInterval(start, end, available)
    assert interval.end == datetime(2026, 3, 9, 19, 30, tzinfo=UTC)
    assert interval.end.tzinfo is UTC
    assert not interval.is_available_at(start)
    assert not interval.is_available_at(end)
    assert not interval.is_available_at(available - timedelta(microseconds=1))
    assert interval.is_available_at(available)
    assert interval.is_available_at(available + timedelta(seconds=1))


@pytest.mark.parametrize("day,hour_utc", [(6, 14), (9, 13)])
def test_cash_open_conversion_across_spring_dst(day: int, hour_utc: int) -> None:
    start = datetime(2026, 3, day, 9, 30, tzinfo=ET)
    interval = BarInterval(start, start + timedelta(minutes=1), start + timedelta(minutes=1))
    assert interval.start == datetime(2026, 3, day, hour_utc, 30, tzinfo=UTC)


@pytest.mark.parametrize("month,day,hour_utc", [(10, 30, 13), (11, 2, 14)])
def test_cash_open_conversion_across_fall_dst(month: int, day: int, hour_utc: int) -> None:
    start = datetime(2026, month, day, 9, 30, tzinfo=ET)
    interval = BarInterval(start, start + timedelta(minutes=1), start + timedelta(minutes=1))
    assert interval.start == datetime(2026, month, day, hour_utc, 30, tzinfo=UTC)


def test_repeated_fall_hour_compares_instants_instead_of_wall_time() -> None:
    # 01:59 EDT precedes 01:00 EST by one minute despite reversed wall-clock ordering.
    start = datetime(2026, 11, 1, 1, 59, tzinfo=ET, fold=0)
    end = datetime(2026, 11, 1, 1, 0, tzinfo=ET, fold=1)
    interval = BarInterval(start, end, end)
    assert interval.end - interval.start == timedelta(minutes=1)


def test_imaginary_spring_wall_time_is_rejected() -> None:
    imaginary = datetime(2026, 3, 8, 2, 30, tzinfo=ET)
    with pytest.raises(ValueError, match="nonexistent"):
        BarInterval(imaginary, imaginary + timedelta(minutes=1), imaginary + timedelta(minutes=2))


@pytest.mark.parametrize("field", ["start", "end", "available_at"])
def test_naive_timestamps_are_rejected(field: str) -> None:
    values = {
        "start": datetime(2026, 1, 1, tzinfo=UTC),
        "end": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        "available_at": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    }
    values[field] = values[field].replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone-aware"):
        BarInterval(**values)


@pytest.mark.parametrize("end_minutes", [-1, 0])
def test_invalid_intervals_are_rejected(end_minutes: int) -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="end must follow"):
        BarInterval(start, start + timedelta(minutes=end_minutes), start + timedelta(minutes=1))


def test_early_availability_and_naive_decision_are_rejected() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(minutes=1)
    with pytest.raises(ValueError, match="before its end"):
        BarInterval(start, end, start)
    with pytest.raises(ValueError, match="timezone-aware"):
        BarInterval(start, end, end).is_available_at(end.replace(tzinfo=None))
