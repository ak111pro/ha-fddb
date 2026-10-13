"""FddbClient.fetch_profile: right URL, parsing, and one re-login when the session expired."""

from __future__ import annotations

import asyncio

from conftest import api, const, parser


def _client(pages):
    """A client whose page requests are answered from ``pages`` in order."""
    client = api.FddbClient(None, "user", "secret")
    client.requested = []
    client.logins = 0

    async def login():
        client.logins += 1
        client._cookie = "cookie"  # noqa: SLF001

    async def get_html(url):
        client.requested.append(url)
        return pages.pop(0)

    client.login = login
    client._get_html = get_html  # noqa: SLF001
    return client


def test_fetch_profile_reads_the_settings_page(load_fixture):
    client = _client([load_fixture("profile_en.html")])
    profile = asyncio.run(client.fetch_profile())
    assert profile.calorie_goal == 2000.0
    assert client.requested == [const.PROFILE_URL]
    assert client.logins == 1


def test_fetch_profile_logs_in_again_once_when_the_session_expired(load_fixture):
    client = _client([load_fixture("diary_logged_out.html"), load_fixture("profile_en.html")])
    profile = asyncio.run(client.fetch_profile())
    assert profile.height_cm == 172.0
    assert client.logins == 2
    assert len(client.requested) == 2


def test_fetch_profile_gives_up_after_the_second_login(load_fixture):
    client = _client([load_fixture("diary_logged_out.html")] * 2)
    try:
        asyncio.run(client.fetch_profile())
    except parser.FddbAuthError:
        pass
    else:
        raise AssertionError("expected FddbAuthError")
