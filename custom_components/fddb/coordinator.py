"""Data coordinator: polls fddb.info and keeps a small local history of daily totals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FddbClient
from .const import (
    BACKFILL_DAYS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FDDB_TZ,
    FINALIZE_TIME,
    KEEP_DAYS,
    REQUEST_PAUSE,
    STORAGE_VERSION,
)
from .parser import DiaryDay, FddbAuthError, FddbError

_LOGGER = logging.getLogger(__name__)

TOTAL_KEYS = ("calories", "fat", "carbs", "sugar", "protein", "fibre")


def fddb_today() -> date:
    return datetime.now(FDDB_TZ).date()


@dataclass(slots=True)
class FddbData:
    """Everything the entities need."""

    today: DiaryDay
    yesterday_calories: float | None
    week_calories: float
    month_calories: float
    avg_7_days: float | None
    avg_30_days: float | None
    streak: int
    last_update: datetime


class FddbCoordinator(DataUpdateCoordinator[FddbData]):
    """Fetches today's diary on a schedule and on demand."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: FddbClient) -> None:
        minutes = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # date iso -> {"calories": .., "fat": .., ..., "products": n, "final": bool}
        self._days: dict[str, dict[str, Any]] = {}
        self.goal: float | None = None
        self._backfilled = False
        self._unsub_finalize = None

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._days = stored.get("days", {})
        self.goal = stored.get("goal")
        self._backfilled = stored.get("backfilled", False)

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(
            lambda: {"days": self._days, "goal": self.goal, "backfilled": self._backfilled},
            10,
        )

    def _remember(self, diary: DiaryDay, final: bool) -> None:
        record = {key: getattr(diary, key) for key in TOTAL_KEYS}
        record["products"] = len(diary.products)
        record["final"] = final
        self._days[diary.day.isoformat()] = record
        cutoff = (fddb_today() - timedelta(days=KEEP_DAYS)).isoformat()
        for key in [k for k in self._days if k < cutoff]:
            del self._days[key]
        self._schedule_save()

    async def async_set_goal(self, value: float | None) -> None:
        self.goal = value
        self._schedule_save()
        self.async_update_listeners()

    # ------------------------------------------------------------------ polling

    async def _fetch(self, day: date) -> DiaryDay:
        try:
            return await self.client.fetch_day(day)
        except FddbAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except FddbError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> FddbData:
        today = fddb_today()
        diary = await self._fetch(today)
        self._remember(diary, final=False)

        # Make sure yesterday has its full value once the day has changed.
        yesterday = (today - timedelta(days=1)).isoformat()
        if yesterday in self._days and not self._days[yesterday]["final"]:
            self._remember(await self._fetch(today - timedelta(days=1)), final=True)

        return self._build(diary)

    def _build(self, today_diary: DiaryDay) -> FddbData:
        today = today_diary.day

        def calories(day: date) -> float | None:
            record = self._days.get(day.isoformat())
            return record["calories"] if record else None

        def logged(day: date) -> bool:
            record = self._days.get(day.isoformat())
            return bool(record and (record["products"] or record["calories"]))

        def total_since(start: date) -> float:
            return sum(
                calories(start + timedelta(days=i)) or 0.0
                for i in range((today - start).days + 1)
            )

        def average(days: int) -> float | None:
            values = [
                calories(today - timedelta(days=i))
                for i in range(1, days + 1)
                if logged(today - timedelta(days=i))
            ]
            return round(sum(values) / len(values), 1) if values else None

        streak = 0
        cursor = today if logged(today) else today - timedelta(days=1)
        while logged(cursor):
            streak += 1
            cursor -= timedelta(days=1)

        return FddbData(
            today=today_diary,
            yesterday_calories=calories(today - timedelta(days=1)),
            week_calories=total_since(today - timedelta(days=today.weekday())),
            month_calories=total_since(today.replace(day=1)),
            avg_7_days=average(7),
            avg_30_days=average(30),
            streak=streak,
            last_update=datetime.now(FDDB_TZ),
        )

    # ------------------------------------------------------------------ background jobs

    @callback
    def async_start_background_jobs(self) -> None:
        """Nightly finalisation of yesterday, plus a one-time history backfill."""
        hour, minute = FINALIZE_TIME
        self._unsub_finalize = async_track_time_change(
            self.hass, self._async_finalize_yesterday, hour=hour, minute=minute, second=0
        )
        self.config_entry.async_on_unload(self._unsub_finalize)
        if not self._backfilled:
            self.config_entry.async_create_background_task(
                self.hass, self._async_backfill(), f"{DOMAIN} backfill"
            )

    async def _async_finalize_yesterday(self, _now: datetime) -> None:
        yesterday = fddb_today() - timedelta(days=1)
        try:
            self._remember(await self.client.fetch_day(yesterday), final=True)
        except FddbError as err:
            _LOGGER.warning("Could not finalise %s: %s", yesterday, err)
            return
        if self.data is not None:
            self.async_set_updated_data(self._build(self.data.today))

    async def _async_backfill(self) -> None:
        today = fddb_today()
        for offset in range(1, BACKFILL_DAYS + 1):
            day = today - timedelta(days=offset)
            if self._days.get(day.isoformat(), {}).get("final"):
                continue
            try:
                self._remember(await self.client.fetch_day(day), final=True)
            except FddbError as err:
                _LOGGER.warning("History backfill stopped at %s: %s", day, err)
                return
            await asyncio.sleep(REQUEST_PAUSE)
        self._backfilled = True
        self._schedule_save()
        if self.data is not None:
            self.async_set_updated_data(self._build(self.data.today))

    async def async_get_day(self, day: date) -> DiaryDay:
        """Fetch any day live (used by the get_diary action)."""
        diary = await self.client.fetch_day(day)
        if day < fddb_today():
            self._remember(diary, final=True)
        return diary
