"""Coordinator behaviour: background jobs and bookkeeping.

Needs Home Assistant itself (skipped without it), see the README's development section.
The coordinator is built on a real ``HomeAssistant`` object inside a running loop, with a fake
client, a fake store and a minimal config entry, so nothing touches the network or the disk.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")


@pytest.fixture(scope="module")
def mods(fddb_ha):
    return SimpleNamespace(
        coordinator=importlib.import_module(f"{fddb_ha}.coordinator"),
        parser=importlib.import_module(f"{fddb_ha}.parser"),
    )


class FakeStore:
    """Stands in for ``homeassistant.helpers.storage.Store``."""

    def __init__(self, stored=None):
        self.stored = stored
        self.saved = []
        self.path = "/nonexistent/.storage/fddb.test"

    async def async_load(self):
        return self.stored

    def async_delay_save(self, data_func, _delay=0):
        self.saved.append(data_func())

    async def async_save(self, data):
        self.saved.append(data)


class FakeClient:
    """Returns prepared diaries or raises prepared errors, in order of the days asked for."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def fetch_day(self, day):
        self.calls.append(day)
        result = self.results(day) if callable(self.results) else self.results
        if isinstance(result, Exception):
            raise result
        return result


def run(mods, client, scenario, store=None, options=None):
    """Run ``scenario(coordinator)`` with a coordinator on a real HomeAssistant object."""
    from homeassistant.core import HomeAssistant

    async def main():
        hass = HomeAssistant("/nonexistent")
        entry = SimpleNamespace(
            options=options or {},
            entry_id="entry1",
            unique_id="user",
            title="user",
            reauth_started=0,
        )
        entry.async_start_reauth = lambda _hass: setattr(
            entry, "reauth_started", entry.reauth_started + 1
        )
        entry.async_on_unload = lambda _func: None
        coordinator = mods.coordinator.FddbCoordinator(hass, entry, client)
        coordinator._store = store or FakeStore()  # noqa: SLF001
        await coordinator.async_load()
        try:
            return await scenario(coordinator)
        finally:
            await hass.async_stop(force=True)

    return asyncio.run(main())


def _diary(mods, day, calories=100.0):
    return mods.parser.DiaryDay(day=day, calories=calories)


def test_backfill_carries_on_after_a_page_that_cannot_be_parsed(mods, monkeypatch):
    monkeypatch.setattr(mods.coordinator, "REQUEST_PAUSE", 0)
    today = mods.coordinator.fddb_today()
    broken = today - timedelta(days=2)

    def results(day):
        if day == broken:
            return mods.parser.FddbParseError("odd page")
        return _diary(mods, day)

    async def scenario(coordinator):
        await coordinator._async_backfill()  # noqa: SLF001
        return coordinator

    client = FakeClient(results)
    coordinator = run(mods, client, scenario)
    assert len(client.calls) == mods.coordinator.BACKFILL_DAYS
    assert broken.isoformat() not in coordinator._days  # noqa: SLF001
    assert (today - timedelta(days=1)).isoformat() in coordinator._days  # noqa: SLF001
    assert (today - timedelta(days=3)).isoformat() in coordinator._days  # noqa: SLF001
    # not marked as done, so the skipped day is tried again after the next restart
    assert coordinator._backfilled is False  # noqa: SLF001


def test_backfill_stops_on_a_connection_error(mods, monkeypatch):
    monkeypatch.setattr(mods.coordinator, "REQUEST_PAUSE", 0)
    today = mods.coordinator.fddb_today()

    def results(day):
        if day == today - timedelta(days=3):
            return mods.parser.FddbConnectionError("down")
        return _diary(mods, day)

    async def scenario(coordinator):
        await coordinator._async_backfill()  # noqa: SLF001
        return coordinator

    client = FakeClient(results)
    coordinator = run(mods, client, scenario)
    assert len(client.calls) == 3
    assert coordinator._backfilled is False  # noqa: SLF001


def test_backfill_completes_when_every_day_works(mods, monkeypatch):
    monkeypatch.setattr(mods.coordinator, "REQUEST_PAUSE", 0)

    async def scenario(coordinator):
        await coordinator._async_backfill()  # noqa: SLF001
        return coordinator

    coordinator = run(mods, FakeClient(lambda day: _diary(mods, day)), scenario)
    assert coordinator._backfilled is True  # noqa: SLF001
    assert len(coordinator._days) == mods.coordinator.BACKFILL_DAYS  # noqa: SLF001


# --- daily calorie goal (#4) ---------------------------------------------------------------


def test_poll_remembers_the_goal_from_fddb_and_keeps_it(mods):
    today = mods.coordinator.fddb_today()
    answers = [
        mods.parser.DiaryDay(day=today, calorie_goal=2400.0),
        mods.parser.DiaryDay(day=today),  # a page that shows no goal keeps the last known one
        mods.parser.DiaryDay(day=today, calorie_goal=2200.0),
    ]

    async def scenario(coordinator):
        seen = []
        for _ in range(3):
            await coordinator._async_update_data()  # noqa: SLF001
            seen.append(coordinator.fddb_goal)
        return seen, coordinator._data()  # noqa: SLF001

    client = FakeClient(lambda day: answers.pop(0) if day == today else _diary(mods, day))
    seen, stored = run(mods, client, scenario)
    assert seen == [2400.0, 2400.0, 2200.0]
    assert stored["fddb_goal"] == 2200.0


def test_stored_goal_is_loaded(mods):
    async def scenario(coordinator):
        return coordinator.fddb_goal, coordinator.goal

    store = FakeStore({"fddb_goal": 2100.0, "goal": 1900.0})
    assert run(mods, FakeClient(None), scenario, store=store) == (2100.0, 1900.0)


@pytest.mark.parametrize(
    ("manual", "fddb", "expected"),
    [
        (None, None, (None, None)),
        (0, None, (None, None)),
        (1800.0, None, (1800.0, "manual")),
        (None, 2400.0, (2400.0, "fddb")),
        (0, 2400.0, (2400.0, "fddb")),
        (1800.0, 2400.0, (1800.0, "manual")),
        (None, 0, (None, None)),
    ],
)
def test_effective_goal(mods, manual, fddb, expected):
    async def scenario(coordinator):
        coordinator.goal = manual
        coordinator.fddb_goal = fddb
        return coordinator.effective_goal

    assert run(mods, FakeClient(None), scenario) == expected


# --- diagnostics bookkeeping (#11) ---------------------------------------------------------


def _clock(monkeypatch, mods, *values):
    """Make the coordinator's stopwatch return ``values`` in turn (two readings per poll)."""
    readings = iter(values)
    monkeypatch.setattr(mods.coordinator, "monotonic", lambda: next(readings))


def test_successful_poll_records_duration_and_time(mods, monkeypatch):
    _clock(monkeypatch, mods, 100.0, 101.2345)
    today = mods.coordinator.fddb_today()

    async def scenario(coordinator):
        before = datetime.now(timezone.utc)
        await coordinator._async_update_data()  # noqa: SLF001
        return coordinator, before

    coordinator, before = run(mods, FakeClient(lambda day: _diary(mods, day)), scenario)
    assert coordinator.last_fetch_duration == 1.234
    assert before <= coordinator.last_success <= datetime.now(timezone.utc)
    assert coordinator.last_success.tzinfo is not None
    assert (coordinator.consecutive_errors, coordinator.total_errors) == (0, 0)
    assert coordinator.last_error is None
    assert today.isoformat() in coordinator._days  # noqa: SLF001


def test_failures_count_up_and_a_success_resets_the_streak(mods, monkeypatch):
    _clock(monkeypatch, mods, 0, 2.5, 10, 10.5, 20, 20.25, 30, 31)
    today = mods.coordinator.fddb_today()
    outcomes = [
        mods.parser.FddbConnectionError("fddb.info answered HTTP 502"),
        mods.parser.FddbParseError("odd page"),
        _diary(mods, today),
        mods.parser.FddbConnectionError("down again"),
    ]
    from homeassistant.helpers.update_coordinator import UpdateFailed

    async def scenario(coordinator):
        seen = []
        for _ in outcomes:
            try:
                await coordinator._async_update_data()  # noqa: SLF001
            except UpdateFailed:
                pass
            seen.append(
                (
                    coordinator.consecutive_errors,
                    coordinator.total_errors,
                    coordinator.last_fetch_duration,
                    coordinator.last_error,
                )
            )
        return coordinator, seen

    queue = list(outcomes)
    client = FakeClient(lambda _day: queue.pop(0))
    coordinator, seen = run(mods, client, scenario)
    assert seen == [
        (1, 1, 2.5, "fddb.info answered HTTP 502"),
        (2, 2, 0.5, "odd page"),
        (0, 2, 0.25, "odd page"),  # streak resets, the last error is kept for reference
        (1, 3, 1.0, "down again"),
    ]
    assert coordinator.last_error_time is not None
    assert coordinator.last_success is not None


def test_auth_failure_counts_too(mods, monkeypatch):
    _clock(monkeypatch, mods, 0, 1)
    from homeassistant.exceptions import ConfigEntryAuthFailed

    async def scenario(coordinator):
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()  # noqa: SLF001
        return coordinator

    coordinator = run(mods, FakeClient(mods.parser.FddbAuthError("bad password")), scenario)
    assert (coordinator.consecutive_errors, coordinator.total_errors) == (1, 1)
    assert coordinator.last_error == "bad password"


def test_long_error_texts_are_cut_and_empty_ones_get_the_type(mods):
    async def scenario(coordinator):
        coordinator._record_failure(RuntimeError("x" * 1000), 1.0)  # noqa: SLF001
        long = coordinator.last_error
        coordinator._record_failure(RuntimeError(), 1.0)  # noqa: SLF001
        return long, coordinator.last_error

    long, empty = run(mods, FakeClient(None), scenario)
    assert len(long) == 255
    assert empty == "RuntimeError"


def test_diagnostics_are_stored_and_restored(mods):
    store = FakeStore()

    async def first(coordinator):
        coordinator._record_failure(RuntimeError("boom"), 1.0)  # noqa: SLF001
        coordinator._record_failure(RuntimeError("boom 2"), 1.0)  # noqa: SLF001
        coordinator._record_success(1.0)  # noqa: SLF001
        return coordinator._data()["diagnostics"]  # noqa: SLF001

    saved = run(mods, FakeClient(None), first, store=store)
    assert saved["total_errors"] == 2
    assert saved["last_error"] == "boom 2"

    async def second(coordinator):
        return coordinator

    restarted = run(mods, FakeClient(None), second, store=FakeStore({"diagnostics": saved}))
    assert restarted.total_errors == 2
    assert restarted.last_error == "boom 2"
    assert restarted.last_success.isoformat() == saved["last_success"]
    assert restarted.last_error_time.isoformat() == saved["last_error_time"]
    # live values start fresh after a restart
    assert restarted.consecutive_errors == 0
    assert restarted.last_fetch_duration is None


@pytest.mark.parametrize("stored", [None, {}, {"diagnostics": {"last_success": "not a date"}}])
def test_missing_or_damaged_diagnostics_are_ignored(mods, stored):
    async def scenario(coordinator):
        return coordinator

    coordinator = run(mods, FakeClient(None), scenario, store=FakeStore(stored))
    assert coordinator.last_success is None
    assert coordinator.total_errors == 0


def test_storage_size_follows_the_file(mods, tmp_path):
    store = FakeStore()
    store.path = str(tmp_path / "fddb.test")

    async def scenario(coordinator):
        missing = coordinator.storage_size
        (tmp_path / "fddb.test").write_bytes(b"x" * 1234)
        await coordinator._async_refresh_storage_size()  # noqa: SLF001
        return missing, coordinator.storage_size

    assert run(mods, FakeClient(None), scenario, store=store) == (None, 1234)
