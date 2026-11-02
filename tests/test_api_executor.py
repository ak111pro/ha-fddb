"""The diary and profile pages are parsed in the executor, never on the event loop."""

from __future__ import annotations

import asyncio
from datetime import date
import threading

from conftest import api


def _client():
    client = api.FddbClient(None, "user", "secret")

    async def login():
        client._cookie = "cookie"  # noqa: SLF001

    async def get_html(*_args):
        return "<html></html>"

    client.login = login
    client._get_html = get_html  # noqa: SLF001
    client._get_diary_html = get_html  # noqa: SLF001
    return client


def _run_and_record(monkeypatch, name, call):
    """Run ``call`` and return (loop thread id, thread id the parser ran in)."""
    seen = {}

    def fake_parser(*_args):
        seen["parser"] = threading.get_ident()
        return name

    monkeypatch.setattr(api, name, fake_parser)

    async def main():
        seen["loop"] = threading.get_ident()
        assert await call(_client()) == name

    asyncio.run(main())
    return seen["loop"], seen["parser"]


def test_diary_is_parsed_off_the_event_loop(monkeypatch):
    loop_thread, parser_thread = _run_and_record(
        monkeypatch, "parse_diary", lambda client: client.fetch_day(date(2026, 11, 2))
    )
    assert parser_thread != loop_thread


def test_profile_is_parsed_off_the_event_loop(monkeypatch):
    loop_thread, parser_thread = _run_and_record(
        monkeypatch, "parse_profile", lambda client: client.fetch_profile()
    )
    assert parser_thread != loop_thread
