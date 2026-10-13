"""The diagnostics download: the profile is included, personal details are not.

Needs Home Assistant itself (skipped without it).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")


def test_diagnostics_contain_the_profile_but_nothing_personal(fddb_ha, load_fixture):
    diagnostics = importlib.import_module(f"{fddb_ha}.diagnostics")
    parser = sys.modules[f"{fddb_ha}.parser"]
    profile = parser.parse_profile(load_fixture("profile_en.html"))
    entry = SimpleNamespace(
        as_dict=lambda: {"title": "someone", "data": {"username": "u", "password": "p"}}
    )
    coordinator = SimpleNamespace(
        data=SimpleNamespace(today=parser.DiaryDay(day=date(2026, 10, 7))),
        last_update_success=True,
        last_exception=None,
        consecutive_errors=0,
        total_errors=0,
        last_error=None,
        last_fetch_duration=1.0,
        last_success=None,
        storage_size=1,
        _days={},
        profile=profile,
        profile_updated=datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc),
        fddb_goal=2000.0,
    )
    entry.runtime_data = coordinator
    result = asyncio.run(diagnostics.async_get_config_entry_diagnostics(None, entry))
    assert result["profile"]["height_cm"] == 172.0
    assert result["profile"]["calorie_goal"] == 2000.0
    assert result["fddb_goal"] == 2000.0
    text = json.dumps(result)
    for personal in ("Max", "testuser", "1990", "Female", "Germany"):
        assert personal not in text
