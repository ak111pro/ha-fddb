"""Data coordinator: polls fddb.info and keeps a small local history of daily totals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
import os
from time import monotonic
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
    PROFILE_REFRESH_INTERVAL,
    PROFILE_RETRY_INTERVAL,
    REQUEST_PAUSE,
    STORAGE_VERSION,
)
from .parser import DiaryDay, FddbAuthError, FddbError, FddbParseError, Profile

_LOGGER = logging.getLogger(__name__)

TOTAL_KEYS = ("calories", "fat", "carbs", "sugar", "protein", "fibre")


def fddb_today() -> date:
    return datetime.now(FDDB_TZ).date()


def _format_time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


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
    yesterday_balance: float | None = None


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
        # The last diary of the current day that was read in full. Stored, so that after a
        # restart the sensors show it while fddb.info cannot be reached (see ``_fallback``).
        self._last_today: DiaryDay | None = None
        # Manual goal (number entity); None or 0 means "use the goal from FDDB".
        self.goal: float | None = None
        # Required calories per day as read from the FDDB settings page, None until one was seen.
        # The fallback for a diary page that does not show the required energy of its day.
        self.fddb_goal: float | None = None
        # Profile values (height, weight, ...) from the same page. Read once at setup and then
        # every PROFILE_REFRESH_INTERVAL; the last known values are kept (and stored) when a
        # refresh fails. ``_profile_next`` is when the next read is due (None = at the next poll).
        self.profile: Profile | None = None
        self.profile_updated: datetime | None = None
        self._profile_next: datetime | None = None
        self._profile_failing = False
        self._backfilled = False
        self._unsub_finalize = None
        # Diagnostics (bookkeeping of the regular poll only, not of background jobs). The time
        # of the last success and the error totals are stored so they survive a restart; the
        # duration, the error streak and the file size are live values.
        self.last_fetch_duration: float | None = None
        self.last_success: datetime | None = None
        self.consecutive_errors = 0
        self.total_errors = 0
        self.last_error: str | None = None
        self.last_error_time: datetime | None = None
        self.storage_size: int | None = None

    # ------------------------------------------------------------------ storage

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._days = stored.get("days", {})
        self._last_today = DiaryDay.from_dict(stored.get("today"))
        self.goal = stored.get("goal")
        self.fddb_goal = stored.get("fddb_goal")
        if stored.get("profile") is not None:
            self.profile = Profile.from_dict(stored["profile"])
            self.profile_updated = _parse_time(stored.get("profile_updated"))
        self._backfilled = stored.get("backfilled", False)
        # Days stored by a version before 0.2.0 have no "balance" (nor "goal"): read the ones the
        # backfill covers once more, so balance yesterday & co. are known again.
        first = (fddb_today() - timedelta(days=BACKFILL_DAYS)).isoformat()
        outdated = [
            key
            for key, record in self._days.items()
            if key >= first and record.get("final") and "balance" not in record
        ]
        for key in outdated:
            self._days[key]["final"] = False
        if outdated:
            self._backfilled = False
        diagnostics = stored.get("diagnostics", {})
        self.last_success = _parse_time(diagnostics.get("last_success"))
        self.total_errors = int(diagnostics.get("total_errors", 0))
        self.last_error = diagnostics.get("last_error")
        self.last_error_time = _parse_time(diagnostics.get("last_error_time"))
        await self._async_refresh_storage_size()

    def _data(self) -> dict[str, Any]:
        return {
            "days": self._days,
            "today": self._last_today.as_dict() if self._last_today else None,
            "goal": self.goal,
            "fddb_goal": self.fddb_goal,
            "profile": self.profile.as_dict() if self.profile else None,
            "profile_updated": _format_time(self.profile_updated),
            "backfilled": self._backfilled,
            "diagnostics": {
                "last_success": _format_time(self.last_success),
                "total_errors": self.total_errors,
                "last_error": self.last_error,
                "last_error_time": _format_time(self.last_error_time),
            },
        }

    async def _async_refresh_storage_size(self) -> None:
        """Read the size of the storage file (None while it does not exist yet).

        The file is written with a delay after changes, so this shows the file as the previous
        save left it; it is refreshed on every poll.
        """

        def _size() -> int | None:
            try:
                return os.stat(self._store.path).st_size
            except OSError:
                return None

        self.storage_size = await self.hass.async_add_executor_job(_size)

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data, 10)

    async def async_flush(self) -> None:
        """Write pending changes now, so a reload never loads stale data."""
        await self._store.async_save(self._data())

    def _remember(self, diary: DiaryDay, final: bool) -> None:
        record = {key: getattr(diary, key) for key in TOTAL_KEYS}
        record["products"] = len(diary.products)
        record["balance"] = diary.balance
        record["goal"] = diary.goal
        record["final"] = final
        self._days[diary.day.isoformat()] = record
        cutoff = (fddb_today() - timedelta(days=KEEP_DAYS)).isoformat()
        for key in [k for k in self._days if k < cutoff]:
            del self._days[key]
        self._schedule_save()

    @property
    def fddb_goal_today(self) -> tuple[float | None, str | None]:
        """The goal FDDB reports for today, and where it was read.

        The required energy of today's diary page (``"fddb_diary"``) wins; when the page does not
        show it, the value of the settings page (``"fddb_profile"``) is the fallback.
        ``(None, None)`` when neither is known.
        """
        diary_goal = self.data.today.goal if self.data is not None else None
        if diary_goal and diary_goal > 0:
            return diary_goal, "fddb_diary"
        if self.fddb_goal and self.fddb_goal > 0:
            return self.fddb_goal, "fddb_profile"
        return None, None

    @property
    def effective_goal(self) -> tuple[float | None, str | None]:
        """The goal used for progress and remaining calories, and where it comes from.

        The number entity wins when it is above 0 (``"manual"``), otherwise the goal FDDB reports
        for today (``"fddb_diary"`` or ``"fddb_profile"``, see ``fddb_goal_today``).
        ``(None, None)`` when none is known.
        """
        if self.goal and self.goal > 0:
            return self.goal, "manual"
        return self.fddb_goal_today

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
        await self._async_refresh_storage_size()
        started = monotonic()
        try:
            data = await self._async_poll()
        except UpdateFailed as err:
            self._record_failure(err, monotonic() - started)
            fallback = self._fallback()
            if fallback is None:
                raise
            # Keep the sensors at sensible values; the problem sensor reports the error.
            level = logging.DEBUG if self.consecutive_errors > 1 else logging.WARNING
            _LOGGER.log(level, "Could not read FDDB, showing the last known values: %s", err)
            return fallback
        except Exception as err:
            self._record_failure(err, monotonic() - started)
            raise
        self._record_success(monotonic() - started)
        # After the bookkeeping, so the fetch duration sensor measures the regular poll only.
        await self._async_refresh_profile()
        return data

    def _record_success(self, duration: float) -> None:
        self.last_fetch_duration = round(duration, 3)
        self.last_success = datetime.now(timezone.utc)
        self.consecutive_errors = 0
        self._schedule_save()

    def _record_failure(self, err: Exception, duration: float) -> None:
        self.last_fetch_duration = round(duration, 3)
        self.consecutive_errors += 1
        self.total_errors += 1
        self.last_error = str(err)[:255] or type(err).__name__
        self.last_error_time = datetime.now(timezone.utc)
        self._schedule_save()

    def _fallback(self) -> FddbData | None:
        """What to show while fetching fails, or None to let the update fail.

        Today's last successful read when there is one (also from before a restart). If what is
        known is from an older day, today counts as a day without entries: yesterday's numbers
        must never show up as today's. Without anything known at all (first setup) there is no
        fallback, so the setup is retried until fddb.info answers.
        """
        today = fddb_today()
        if self._last_today is not None and self._last_today.day == today:
            return self._build(self._last_today)
        if self._last_today is None and self.data is None and not self._days:
            return None
        return self._build(DiaryDay(day=today))

    async def _async_poll(self) -> FddbData:
        today = fddb_today()
        diary = await self._fetch(today)
        self._last_today = diary
        self._remember(diary, final=False)

        # Make sure yesterday has its full value once the day has changed.
        yesterday = (today - timedelta(days=1)).isoformat()
        if yesterday in self._days and not self._days[yesterday]["final"]:
            self._remember(await self._fetch(today - timedelta(days=1)), final=True)

        return self._build(diary)

    async def _async_refresh_profile(self) -> None:
        """Read the settings page when it is due. Never raises: the diary matters more.

        The last known profile stays in place when a read fails, and the next try is made after
        PROFILE_RETRY_INTERVAL instead of at every poll.
        """
        now = datetime.now(timezone.utc)
        if self._profile_next is not None and now < self._profile_next:
            return
        try:
            profile = await self.client.fetch_profile()
        except FddbAuthError:
            # The diary was just read with this session, so this is unexpected: ask for a new
            # login rather than retrying a rejected password every hour.
            self._profile_next = now + PROFILE_RETRY_INTERVAL
            self.config_entry.async_start_reauth(self.hass)
            return
        except FddbError as err:
            self._profile_next = now + PROFILE_RETRY_INTERVAL
            level = logging.DEBUG if self._profile_failing else logging.WARNING
            _LOGGER.log(level, "Could not read the FDDB profile page: %s", err)
            self._profile_failing = True
            return
        self._profile_failing = False
        self._profile_next = now + PROFILE_REFRESH_INTERVAL
        self.profile = profile
        self.profile_updated = now
        # What FDDB shows now is the goal; a page that no longer shows it clears the old value.
        self.fddb_goal = profile.calorie_goal
        self._schedule_save()

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
                calories(start + timedelta(days=i)) or 0.0 for i in range((today - start).days + 1)
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
            yesterday_balance=self._days.get((today - timedelta(days=1)).isoformat(), {}).get(
                "balance"
            ),
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
        except FddbAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return
        except FddbError as err:
            _LOGGER.warning("Could not finalise %s: %s", yesterday, err)
            return
        if self.data is not None:
            self.async_set_updated_data(self._build(self.data.today))

    async def _async_backfill(self) -> None:
        today = fddb_today()
        skipped = 0
        for offset in range(1, BACKFILL_DAYS + 1):
            day = today - timedelta(days=offset)
            if self._days.get(day.isoformat(), {}).get("final"):
                continue
            try:
                self._remember(await self.client.fetch_day(day), final=True)
            except FddbAuthError:
                self.config_entry.async_start_reauth(self.hass)
                return
            except FddbParseError as err:
                # One odd day must not leave the rest of the history empty (fddb-exporter 2.5.0
                # also carries on after a single failing day). Connection errors still stop the
                # run, since every following day would fail the same way.
                skipped += 1
                _LOGGER.warning("History backfill skipped %s: %s", day, err)
            except FddbError as err:
                _LOGGER.warning("History backfill stopped at %s: %s", day, err)
                return
            await asyncio.sleep(REQUEST_PAUSE)
        if not skipped:
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
