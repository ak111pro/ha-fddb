"""Start of the day, week and month in FDDB time (no Home Assistant imports)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .const import FDDB_TZ


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=FDDB_TZ)


def day_start(day: date) -> datetime:
    """Midnight (German time) at the start of ``day``."""
    return _midnight(day)


def week_start(day: date) -> datetime:
    """Midnight of the Monday of the week that contains ``day``."""
    return _midnight(day - timedelta(days=day.weekday()))


def month_start(day: date) -> datetime:
    """Midnight of the first of the month that contains ``day``."""
    return _midnight(day.replace(day=1))
