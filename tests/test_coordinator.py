"""Coordinator behaviour: background jobs and bookkeeping.

Needs Home Assistant itself (skipped without it), see the README's development section.
The coordinator is built on a real ``HomeAssistant`` object inside a running loop, with a fake
client, a fake store and a minimal config entry, so nothing touches the network or the disk.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
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
