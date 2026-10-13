"""Period starts used for ``last_reset``."""

from __future__ import annotations

from datetime import date, datetime

from conftest import const
from custom_components.fddb import periods


def test_day_start_is_midnight_in_berlin():
    start = periods.day_start(date(2026, 10, 7))
    assert start == datetime(2026, 10, 7, 0, 0, tzinfo=const.FDDB_TZ)
    assert start.utcoffset().total_seconds() == 2 * 3600  # CEST


def test_utc_offset_follows_daylight_saving():
    assert periods.day_start(date(2026, 1, 15)).utcoffset().total_seconds() == 3600


def test_week_starts_on_monday():
    # 2026-10-07 is a Wednesday
    assert periods.week_start(date(2026, 10, 7)).date() == date(2026, 10, 5)
    assert periods.week_start(date(2026, 10, 5)).date() == date(2026, 10, 5)
    assert periods.week_start(date(2026, 10, 11)).date() == date(2026, 10, 5)  # Sunday


def test_week_start_crosses_month_and_year():
    assert periods.week_start(date(2026, 1, 1)).date() == date(2025, 12, 29)


def test_month_start():
    assert periods.month_start(date(2026, 10, 31)).date() == date(2026, 10, 1)
    assert periods.month_start(date(2026, 2, 1)).date() == date(2026, 2, 1)
