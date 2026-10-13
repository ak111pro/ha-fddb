"""Tests for the FDDB day window (needs aiohttp for the module import only)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from custom_components.fddb.api import diary_window
from custom_components.fddb.const import FDDB_TZ


def test_known_value():
    assert diary_window(date(2024, 8, 27)) == (1724716800, 1724803199)


def test_window_spans_one_day_minus_one_second():
    start, end = diary_window(date(2026, 1, 15))
    assert end - start == 86399


@pytest.mark.parametrize(
    ("day", "hours"),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25), (date(2026, 7, 1), 24)],
)
def test_window_follows_the_real_length_of_the_day(day, hours):
    # fddb-exporter 2.5.0: each day's boundary is resolved separately, so DST days are 23/25 h.
    start, end = diary_window(day)
    assert end - start + 1 == hours * 3600
    assert datetime.fromtimestamp(start, tz=FDDB_TZ).date() == day


def test_consecutive_windows_have_no_gap_and_no_overlap():
    day = date(2026, 1, 1)
    while day.year == 2026:
        _, end = diary_window(day)
        next_start, _ = diary_window(day + timedelta(days=1))
        assert next_start == end + 1, day
        day += timedelta(days=1)


def test_dst_change_days_hit_expected_epochs():
    # 2026-03-29: Berlin midnight is 23:00 UTC the day before; +2 h wall clock hits the gap.
    assert diary_window(date(2026, 3, 29))[0] == int(
        datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc).timestamp()
    )
    # 2026-10-25: Berlin midnight is 22:00 UTC the day before; +2 h is 00:00 UTC.
    assert diary_window(date(2026, 10, 25))[0] == int(
        datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc).timestamp()
    )


def test_window_start_is_always_inside_the_requested_german_day():
    # The window is only used to select a day; its start must fall on that local date
    # for every day of a year, including both DST changes.
    day = date(2026, 1, 1)
    while day.year == 2026:
        start, _ = diary_window(day)
        assert datetime.fromtimestamp(start, tz=FDDB_TZ).date() == day, day
        day += timedelta(days=1)
