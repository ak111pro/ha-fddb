"""Tests for the page variants fddb.info serves instead of data since the 2026 redesign.

Three shapes were observed logged-out on 2026-10-28:

1. Login form page (``diary_login_form_*.html``): the account page with a
   ``form action="...&action=login"``. Detected by path 2 of ``is_logged_out``.
2. Notepad page (``diary_notepad_en.html``): the "Food Diary" notepad served
   with HTTP 200 where ``myday20/`` used to redirect; login is only a plain
   menu link, so no detection path matches.
3. Fetch error page (``diary_fetch_error_en.html``): "This is currently not
   possible … please try again later" with HTTP 200. Also matches no path.

The login-disabled variant (``diary_login_disabled_en.html``) covers the
reported "login temporarily disabled" flavour; its wording is synthetic.
"""

from __future__ import annotations

from datetime import date

from bs4 import BeautifulSoup
import pytest

from custom_components.fddb.parser import (
    FddbAuthError,
    FddbParseError,
    is_logged_out,
    parse_diary,
    parse_profile,
)

DAY = date(2026, 10, 28)

LOGIN_FORM_PAGES = [
    "diary_login_form_en.html",
    "diary_login_form_de.html",
    "diary_login_disabled_en.html",
]
NON_DETECTED_PAGES = ["diary_notepad_en.html", "diary_fetch_error_en.html"]


def _soup(load_fixture, name):
    return BeautifulSoup(load_fixture(name), "html.parser")


# --- is_logged_out(): each detection path directly ------------------------------------------


def test_logout_link_wins_over_login_link():
    """Path 1: a page offering logout is logged in even if a login link exists too."""
    html = """
    <html><body>
      <ul class="topmenu">
        <li><a href="/db/i18n/account/?lang=en&amp;action=login">Login</a></li>
        <li><a href="/db/i18n/account/?lang=en&amp;action=logout">Logout</a></li>
      </ul>
    </body></html>
    """
    assert is_logged_out(BeautifulSoup(html, "html.parser")) is False


def test_login_form_without_link_counts():
    """Path 2: only a POST form (no login anchor) must still be detected."""
    html = """
    <html><body>
      <form action="/db/i18n/account/?lang=en&amp;action=login" method="POST">
        <input name="user_name"><input name="password">
      </form>
    </body></html>
    """
    assert is_logged_out(BeautifulSoup(html, "html.parser")) is True


def test_old_quicklinks_login_still_detected():
    """Path 3: a quicklinks "Login"/"Anmelden" anchor without an action query."""
    html = """
    <html><body>
      <div class="quicklinks"><a class="v2hdlnk" href="/db/i18n/account/?lang=de">Anmelden</a></div>
    </body></html>
    """
    assert is_logged_out(BeautifulSoup(html, "html.parser")) is True


def test_login_disabled_page_is_detected(load_fixture):
    """The disabled-login page keeps the form with action=login, just without inputs."""
    assert is_logged_out(_soup(load_fixture, "diary_login_disabled_en.html")) is True


# --- Negative control: real logged-in pages must not be flagged ------------------------------


def test_redesign_logged_in_pages_not_flagged(load_fixture):
    """diary_day_en.html (logout link) and profile_en.html stay logged in."""
    assert is_logged_out(_soup(load_fixture, "diary_day_en.html")) is False
    assert is_logged_out(_soup(load_fixture, "profile_en.html")) is False


# --- Login-form pages: full pipeline raises the auth error -----------------------------------


@pytest.mark.parametrize("fixture", LOGIN_FORM_PAGES)
def test_login_form_diary_raises_auth_error(load_fixture, fixture):
    with pytest.raises(FddbAuthError):
        parse_diary(load_fixture(fixture), DAY)


@pytest.mark.parametrize("fixture", LOGIN_FORM_PAGES)
def test_login_form_profile_raises_auth_error(load_fixture, fixture):
    with pytest.raises(FddbAuthError):
        parse_profile(load_fixture(fixture))


# --- Notepad / fetch-error pages: currently invisible to the integration ----------------------
# These pages contain no login marker at all, so is_logged_out() misses them and
# parse_diary() accepts the missing totals table as an empty day: HA shows
# "0 kcal" instead of an auth/connection problem. The two diary tests below are
# strict xfails documenting the desired behaviour (raise instead of returning
# zeros); they start failing loudly (= XPASS) once the parser detects these pages.

# TODO(parser): detect the notepad page (title "Food Diary" with a plain login
# menu link instead of a totals table) and raise FddbAuthError, and map the
# "This is currently not possible" error page to FddbConnectionError.


@pytest.mark.xfail(
    strict=True,
    reason="notepad page is not detected as logged out; parse_diary silently returns an empty day",
)
def test_notepad_page_raises_auth_error(load_fixture):
    with pytest.raises(FddbAuthError):
        parse_diary(load_fixture("diary_notepad_en.html"), DAY)


@pytest.mark.xfail(
    strict=True,
    reason="fetch-error page is not detected; parse_diary silently returns an empty day",
)
def test_fetch_error_page_raises(load_fixture):
    html = load_fixture("diary_fetch_error_en.html")
    with pytest.raises((FddbAuthError, FddbParseError)):
        parse_diary(html, DAY)


def test_notepad_and_fetch_error_current_behaviour(load_fixture):
    """Current (buggy) behaviour pinned explicitly so the xfails above are explained."""
    for fixture in NON_DETECTED_PAGES:
        html = load_fixture(fixture)
        assert is_logged_out(BeautifulSoup(html, "html.parser")) is False
        day = parse_diary(html, DAY)
        assert day.calories == 0.0
        assert not day.has_entries
        # The same pages are not parseable as a profile at least.
        with pytest.raises(FddbParseError):
            parse_profile(html)


# --- Regression: the pre-redesign fixtures keep working exactly as before ---------------------


@pytest.mark.parametrize("fixture", ["diary_logged_out.html", "diary_logged_out_de.html"])
def test_old_logged_out_fixtures_still_raise(load_fixture, fixture):
    with pytest.raises(FddbAuthError):
        parse_diary(load_fixture(fixture), DAY)


def test_old_logged_in_fixtures_still_parse(load_fixture):
    day = parse_diary(load_fixture("diary_normal.html"), DAY)
    assert day.calories == 363
    assert is_logged_out(_soup(load_fixture, "diary_normal.html")) is False
