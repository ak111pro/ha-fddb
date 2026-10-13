"""Constants for the FDDB integration."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

DOMAIN = "fddb"

BASE_URL = "https://fddb.info"
LOGIN_URL = f"{BASE_URL}/db/i18n/account/?lang=de&action=login"
# The diary is always requested in English: the parser relies on the English labels.
DIARY_URL = f"{BASE_URL}/db/i18n/myday20/?lang=en&p={{start}}&q={{end}}"
# The settings page with the profile (height, weight, required calories per day, ...). Also in
# English, for the same reason.
PROFILE_URL = f"{BASE_URL}/db/i18n/profile20/?lang=en"
# Where the user opens their diary in a browser (device "Visit" link). The desktop diary page
# (myday20) answers with an error page unless the browser is logged in; the mobile notepad
# redirects to the login page instead and shows the diary after signing in.
DIARY_WEB_URL = "https://fddb.mobi/notepad/"
SESSION_COOKIE = "fddb"

# FDDB diary days follow German local time, whatever the Home Assistant time zone is.
FDDB_TZ = ZoneInfo("Europe/Berlin")

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 30  # minutes
MIN_UPDATE_INTERVAL = 10
MAX_UPDATE_INTERVAL = 1440

# Days fetched once after setup so that averages and period sums have data right away.
BACKFILL_DAYS = 31
# Days kept in local storage (enough for monthly sums and 30-day averages).
KEEP_DAYS = 400
# Pause between consecutive diary requests during backfill, to be gentle on fddb.info.
REQUEST_PAUSE = 1.5

# The profile changes rarely, so it is read once at setup and then only every few hours (and
# again after a failure, a bit sooner), not on every poll.
PROFILE_REFRESH_INTERVAL = timedelta(hours=6)
PROFILE_RETRY_INTERVAL = timedelta(hours=1)

# Yesterday is re-read once at night so its values are final.
FINALIZE_TIME = (3, 15)

STORAGE_VERSION = 1
REQUEST_TIMEOUT = 30

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_DATE = "date"
SERVICE_REFRESH = "refresh"
SERVICE_GET_DIARY = "get_diary"

UPDATE_INTERVAL_DEFAULT = timedelta(minutes=DEFAULT_UPDATE_INTERVAL)
