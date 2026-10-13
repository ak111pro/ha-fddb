"""Constants that users see in Home Assistant."""

from __future__ import annotations

from urllib.parse import urlparse

from conftest import const


def test_diary_web_url_is_a_working_https_page():
    url = urlparse(const.DIARY_WEB_URL)
    assert url.scheme == "https"
    assert url.netloc == "fddb.mobi"
    assert url.path == "/notepad/"


def test_diary_web_url_is_not_the_scraped_desktop_page():
    # myday20 is what the integration reads with its own session; browsers without a
    # login get a server error there, so it must not be the device link.
    assert "myday20" not in const.DIARY_WEB_URL


def test_profile_url_is_the_english_settings_page():
    # the parser relies on the English labels, like for the diary
    assert const.PROFILE_URL == "https://fddb.info/db/i18n/profile20/?lang=en"
    assert "lang=en" in const.DIARY_URL


def test_profile_is_refreshed_every_few_hours_not_every_poll():
    assert const.PROFILE_REFRESH_INTERVAL >= const.UPDATE_INTERVAL_DEFAULT * 4
    assert const.PROFILE_RETRY_INTERVAL < const.PROFILE_REFRESH_INTERVAL
