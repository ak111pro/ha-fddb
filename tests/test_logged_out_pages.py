"""Tests for the page variants fddb.info serves instead of data since the 2026 redesign.

Every fixture documents its own provenance (live capture vs synthetic) in an
HTML comment. All URL behaviour below was verified with ``curl -L`` on
2026-10-28 while logged out (HTTP status and final URL only, one request per
URL); the results are recorded in the fixture headers.

Live-verified page variants:

1. Login form page (``diary_login_form_en.html`` from the live account page,
   ``diary_login_form_de.html`` synthetic): ``profile20/?lang=en`` redirects
   to ``account/?lang=en&nomobile=1&returnurl=...`` (HTTP 200), which contains
   a ``form action="...&action=login"``. Detected by path 2 of
   ``is_logged_out``.
2. Notepad page (``diary_notepad_en.html`` from the live notepad URL):
   "Food Diary" served with HTTP 200. Login is only a plain menu link, so no
   detection path matches — the integration currently sees an empty day.
   ``myday20/?lang=en`` without query parameters also ends up here, but the
   diary URL with a date range (see 3) does not.
3. Diary "Details" page (``diary_logged_out_details_en.html`` from a live
   capture): the URL the integration actually requests,
   ``myday20/?lang=en&p=...&q=...``, answers with a separate "Details" day
   page (HTTP 200, no redirect) that shows "0 kJ (0 kcal) from 0 food items"
   with no login form and no logout link. It matches none of the
   ``is_logged_out`` paths, so the integration reports 0 kcal while being
   logged out — the first fixture of this module is a strict xfail that
   documents this real bug against the current parser.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from custom_components.fddb import const
from custom_components.fddb.parser import (
    FddbAuthError,
    is_logged_out,
    parse_diary,
    parse_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- what the current parser does with the live captures ----------------


@pytest.mark.parametrize("fixture", ["diary_login_form_en.html", "diary_login_form_de.html"])
def test_login_form_page_detected_as_logged_out(fixture: str) -> None:
    """The account/login pages are detected by the form action=login path."""
    assert is_logged_out(BeautifulSoup(load(fixture), "html.parser"))


@pytest.mark.parametrize("fixture", ["diary_notepad_en.html", "diary_logged_out_details_en.html"])
def test_plain_login_link_alone_is_not_detected(fixture: str) -> None:
    """Notepad and Details pages only carry a plain topbar "Login" link."""
    soup = BeautifulSoup(load(fixture), "html.parser")
    assert not is_logged_out(soup)
    assert soup.select_one('a[href*="account"]')


def test_diary_notepad_parses_as_empty_day() -> None:
    """The current parser sees the notepad page as a valid but empty day."""
    result = parse_diary(load("diary_notepad_en.html"), date(2026, 10, 28))
    assert result.calories == 0.0
    assert not result.has_entries


@pytest.mark.xfail(
    strict=True,
    reason="Real bug (live capture): the logged-out 'Details' day page is a plain "
    "HTTP 200 with '0 kJ (0 kcal) from 0 food items' and no login form, so the "
    "current parser reports 0 kcal for a logged-out session instead of raising "
    "FddbAuthError.",
)
def test_details_page_logged_out_is_not_reported_as_zero_kcal() -> None:
    """The Details day page the integration really gets must not read as valid data."""
    html = load("diary_logged_out_details_en.html")
    result = parse_diary(html, date(2026, 10, 26))
    assert not result.has_entries and result.calories == 0.0
    assert False, "logged-out Details page parsed as a valid empty day"


# -- what the fixtures document about the pages themselves --------------


def test_details_page_shows_zero_kcal_and_no_food_items() -> None:
    """Live capture: the logged-out Details page states an empty day in plain text."""
    soup = BeautifulSoup(load("diary_logged_out_details_en.html"), "html.parser")
    subline = soup.select_one("div.fddb-myday-subline")
    assert subline is not None
    text = subline.get_text(" ", strip=True)
    assert "0 kcal" in text
    assert "0 food items" in text


def test_details_page_has_login_link_but_no_login_form() -> None:
    """Login is offered only as a topbar link, so the integration cannot recover."""
    soup = BeautifulSoup(load("diary_logged_out_details_en.html"), "html.parser")
    assert soup.select_one('a[href*="account"]')
    assert not soup.select('form[action*="login"]')
    assert not soup.select('a[action*="login"]')


@pytest.mark.parametrize(
    "fixture",
    ["diary_notepad_en.html", "diary_logged_out_details_en.html"],
)
def test_logged_out_pages_do_not_match_logged_in_markers(fixture: str) -> None:
    """The redesign keeps the Login link where logged-in pages keep Logout."""
    soup = BeautifulSoup(load(fixture), "html.parser")
    assert not any(link.text.strip().lower() == "logout" for link in soup.find_all("a"))
    assert soup.title and "Fddb" in soup.title.get_text()


@pytest.mark.parametrize(
    "fixture",
    [
        "diary_day_en.html",
        "diary_empty.html",
        "diary_full.html",
        "diary_meals.html",
        "diary_normal.html",
        "profile_en.html",
    ],
)
def test_logged_in_fixtures_keep_logout_link(fixture: str) -> None:
    """Regression guard: every logged-in fixture carries the logout marker that
    the logged-out captures lack (diary_empty is a logged-in empty day)."""
    soup = BeautifulSoup(load(fixture), "html.parser")
    assert any(link.text.strip().lower() == "logout" for link in soup.find_all("a"))
    assert not soup.select('form[action*="login"]')


def test_notepad_page_structure() -> None:
    """Document what the captured notepad page contains: headings but no data."""
    soup = BeautifulSoup(load("diary_notepad_en.html"), "html.parser")
    assert soup.h1
    assert "food diary" in soup.h1.get_text().lower()
    assert "No entries" in soup.get_text(" ", strip=True)


def test_login_form_pages_require_credentials() -> None:
    """The integration has no credentials, so these pages are fatal for it."""
    for fixture, language_marker in (
        ("diary_login_form_en.html", "E-mail"),
        ("diary_login_form_de.html", "E-Mail"),
    ):
        html = load(fixture)
        assert language_marker in html
        with pytest.raises(FddbAuthError):
            parse_profile(html)
        with pytest.raises(FddbAuthError):
            parse_diary(html, date(2026, 10, 28))


# -- URL contract tests: they must not silently move to another page ----


def test_integration_urls_unchanged() -> None:
    """The fixtures document these exact URLs; changing them changes which page
    fddb.info serves and which of the cases above applies. The diary URL is the
    one whose logged-out behaviour differs from the parameterless variant."""
    assert const.DIARY_URL == "https://fddb.info/db/i18n/myday20/?lang=en&p={start}&q={end}"
    assert const.PROFILE_URL == "https://fddb.info/db/i18n/profile20/?lang=en"
    assert const.LOGIN_URL == "https://fddb.info/db/i18n/account/?lang=de&action=login"
    assert const.DIARY_WEB_URL == "https://fddb.mobi/notepad/"
