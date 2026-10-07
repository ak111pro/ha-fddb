"""Minimal async client for the fddb.info food diary."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
import logging

import aiohttp

from .const import (
    DIARY_URL,
    FDDB_TZ,
    LOGIN_URL,
    REQUEST_TIMEOUT,
    SESSION_COOKIE,
)
from .parser import (
    DiaryDay,
    FddbAuthError,
    FddbConnectionError,
    FddbError,
    parse_diary,
)

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "ha-fddb (Home Assistant integration; +https://github.com/ak111pro/ha-fddb)"


def diary_window(day: date) -> tuple[int, int]:
    """Return the (start, end) epoch seconds FDDB expects for one diary day.

    FDDB uses German local days; starting two hours after midnight keeps the window
    inside the right day on both sides of a daylight-saving change.
    """
    start = datetime.combine(day, time(0), tzinfo=FDDB_TZ) + timedelta(hours=2)
    start_ts = int(start.timestamp())
    return start_ts, start_ts + 86400 - 1


class FddbClient:
    """Logs in once, keeps the session cookie and re-logs in when it expires."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._cookie: str | None = None
        self._lock = asyncio.Lock()

    async def login(self) -> None:
        """Log in and keep the session cookie. Raises FddbAuthError on bad credentials."""
        try:
            async with self._session.post(
                LOGIN_URL,
                data={
                    "loginemailorusername": self._username,
                    "loginpassword": self._password,
                },
                headers={"User-Agent": USER_AGENT},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                cookie = resp.cookies.get(SESSION_COOKIE)
                status = resp.status
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FddbConnectionError(f"Could not reach fddb.info: {err}") from err

        if cookie is None or not cookie.value:
            _LOGGER.debug("Login rejected by fddb.info (HTTP %s, no session cookie)", status)
            raise FddbAuthError("Login to fddb.info failed, check username and password")
        self._cookie = cookie.value

    async def _get_diary_html(self, day: date) -> str:
        start, end = diary_window(day)
        url = DIARY_URL.format(start=start, end=end)
        try:
            async with self._session.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Cookie": f"{SESSION_COOKIE}={self._cookie}",
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status >= 500:
                    raise FddbConnectionError(f"fddb.info answered HTTP {resp.status}")
                resp.raise_for_status()
                return await resp.text(encoding="utf-8", errors="replace")
        except aiohttp.ClientResponseError as err:
            raise FddbConnectionError(f"fddb.info answered HTTP {err.status}") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FddbConnectionError(f"Could not reach fddb.info: {err}") from err

    async def fetch_day(self, day: date) -> DiaryDay:
        """Fetch and parse one diary day, logging in (again) when needed."""
        async with self._lock:
            if self._cookie is None:
                await self.login()
            try:
                return parse_diary(await self._get_diary_html(day), day)
            except FddbAuthError:
                _LOGGER.debug("FDDB session expired, logging in again")
                await self.login()
                return parse_diary(await self._get_diary_html(day), day)

    async def validate(self) -> None:
        """Log in and read today's page once (used by the config flow)."""
        self._cookie = None
        await self.fetch_day(datetime.now(FDDB_TZ).date())


__all__ = ["FddbClient", "FddbError", "diary_window"]
