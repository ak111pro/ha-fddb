"""Macronutrient shares of energy."""

from __future__ import annotations

from datetime import date

import pytest

from conftest import parser


def _day(**values: float) -> parser.DiaryDay:
    return parser.DiaryDay(day=date(2026, 10, 7), **values)


@pytest.mark.parametrize("macro", ["protein", "carbs", "fat"])
def test_share_is_zero_when_nothing_is_logged(macro):
    assert _day().macro_share(macro) == 0.0


@pytest.mark.parametrize("macro", ["protein", "carbs", "fat"])
def test_share_is_zero_for_calories_without_macros(macro):
    # e.g. black coffee: calories logged but no fat/carbs/protein
    assert _day(calories=2.0).macro_share(macro) == 0.0


def test_shares_use_4_4_9_kcal_per_gram_and_add_up_to_100():
    day = _day(protein=100.0, carbs=100.0, fat=100.0)
    # 400 + 400 + 900 kcal
    assert day.macro_share("protein") == 23.5
    assert day.macro_share("carbs") == 23.5
    assert day.macro_share("fat") == 52.9
    total = sum(day.macro_share(m) for m in ("protein", "carbs", "fat"))
    assert total == pytest.approx(100.0, abs=0.2)


def test_single_macro_is_100_percent():
    day = _day(protein=50.0)
    assert day.macro_share("protein") == 100.0
    assert day.macro_share("fat") == 0.0


def test_share_from_parsed_empty_day(load_fixture):
    day = parser.parse_diary(load_fixture("diary_empty.html"), date(2026, 10, 7))
    assert day.macro_share("fat") == 0.0
