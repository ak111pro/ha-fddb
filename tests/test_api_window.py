"""Tests for the FDDB day window (needs aiohttp for the module import only)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from custom_components.fddb.api import diary_window
from custom_components.fddb.const import FDDB_TZ


def test_known_value():
    assert diary_window(date(2024, 8, 27)) == (1724716800, 1724803199)


def test_window_spans_one_day_minus_one_second():
    start, end = diary_window(date(2026, 1, 15))
    assert end - start == 86399


@pytest.mark.parametrize("day", [date(2026, 3, 29), date(2026, 10, 25)])
def test_dst_change_days_stay_inside_the_utc_day(day):
    start, end = diary_window(day)
    assert end - start == 86399
    start_utc = datetime.fromtimestamp(start, tz=timezone.utc)
    end_utc = datetime.fromtimestamp(end, tz=timezone.utc)
    assert start_utc.date() == day
    assert end_utc.date() == day or end_utc.date() == date.fromordinal(day.toordinal() + 1)


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
        day = date.fromordinal(day.toordinal() + 1)
