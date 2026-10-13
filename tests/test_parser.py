"""Tests for the diary parser, using synthetic HTML fixtures."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.fddb import parser as parser_module
from custom_components.fddb.parser import (
    DiaryDay,
    FddbAuthError,
    FddbParseError,
    Profile,
    parse_diary,
    parse_profile,
)

DAY = date(2026, 10, 7)


@pytest.fixture
def normal_html(load_fixture) -> str:
    return load_fixture("diary_normal.html")


@pytest.fixture
def normal(normal_html) -> DiaryDay:
    return parse_diary(normal_html, DAY)


def test_totals(normal):
    assert normal.day == DAY
    assert normal.calories == 363
    assert normal.fat == 11.5
    assert normal.carbs == 270.0
    assert normal.protein == 14.1
    assert normal.sugar == 31.4
    assert normal.fibre == 6.2
    assert normal.has_entries


def test_category_rows_are_skipped(normal):
    names = [p.name for p in normal.products]
    assert "Breakfast" not in names
    assert "Lunch" not in names
    assert len(normal.products) == 4


def test_product_split_into_amount_and_name(normal):
    oatmeal, milk, apple, _coffee = normal.products
    assert (oatmeal.amount, oatmeal.name) == ("150 g", "Oatmeal")
    # Name may contain spaces and digits; only the first two tokens are the amount.
    assert (milk.amount, milk.name) == ("250 ml", "Whole milk 3.5%")
    assert (apple.amount, apple.name) == ("1 piece", "Apple")


def test_product_values_link_and_time(normal):
    oatmeal = normal.products[0]
    assert oatmeal.calories == 146
    assert oatmeal.fat == 2.5
    assert oatmeal.protein == 5.1
    assert oatmeal.link == "/db/en/food/test/oatmeal/index.html"
    assert oatmeal.time == "08:15"


def test_bread_unit_carbs_cell_uses_grams_only(normal):
    # "246.2 g (20.5 BE)" must yield 246.2, not 246.220.5.
    assert normal.products[0].carbs == 246.2
    # Same for the footer cell "270.0 g (22.5 BE)".
    assert normal.carbs == 270.0


def test_product_name_without_amount(normal):
    coffee = normal.products[3]
    assert coffee.amount is None
    assert coffee.name == "Coffee"
    assert coffee.time is None
    assert coffee.calories == 2


def test_product_values_sum_to_totals(normal):
    assert sum(p.calories for p in normal.products) == pytest.approx(normal.calories)
    assert sum(p.fat for p in normal.products) == pytest.approx(normal.fat)
    assert sum(p.carbs for p in normal.products) == pytest.approx(normal.carbs)
    assert sum(p.protein for p in normal.products) == pytest.approx(normal.protein)


def test_empty_day_without_table(load_fixture):
    diary = parse_diary(load_fixture("diary_empty.html"), DAY)
    assert diary == DiaryDay(day=DAY)
    assert diary.products == []
    assert diary.calories == 0
    assert not diary.has_entries


@pytest.mark.parametrize("fixture", ["diary_logged_out.html", "diary_logged_out_de.html"])
def test_logged_out_page_raises_auth_error(load_fixture, fixture):
    with pytest.raises(FddbAuthError):
        parse_diary(load_fixture(fixture), DAY)


def test_missing_sugar_row_raises_parse_error(normal_html):
    html = normal_html.replace("thereof Sugar", "something else")
    with pytest.raises(FddbParseError, match="sugar"):
        parse_diary(html, DAY)


def test_missing_fibre_row_raises_parse_error(normal_html):
    html = normal_html.replace("Dietary fibre", "something else")
    with pytest.raises(FddbParseError, match="fib"):
        parse_diary(html, DAY)


def test_bad_number_in_footer_raises_parse_error(normal_html):
    html = normal_html.replace("<b>363 kcal</b>", "<b>n/a</b>")
    with pytest.raises(FddbParseError, match="Not a number"):
        parse_diary(html, DAY)


def test_bad_number_in_product_row_raises_parse_error(normal_html):
    html = normal_html.replace("<span>146 kcal</span>", "<span>-</span>")
    with pytest.raises(FddbParseError, match="Not a number"):
        parse_diary(html, DAY)


def test_bad_number_in_nutrient_row_raises_parse_error(normal_html):
    html = normal_html.replace("<span>31.4 g</span>", "<span>? g</span>")
    with pytest.raises(FddbParseError):
        parse_diary(html, DAY)


def test_footer_with_too_few_cells_raises_parse_error(normal_html):
    html = normal_html.replace(
        '<tr class="myday-table-std-td-footer">',
        '<tr class="myday-table-std-td-footer"><td>x</td></tr><tr>',
    )
    # The last row now only has one cell less than required for totals.
    html = html.replace("<td><b>14.1 g</b></td>", "")
    with pytest.raises(FddbParseError, match="totals"):
        parse_diary(html, DAY)


def test_own_food_without_link_is_read_from_cell_text(normal_html):
    # Own foods and recipes have no link to the food database (seen live 2026-10-07).
    html = normal_html.replace(
        '<a href="/db/en/food/test/coffee/index.html">Coffee</a>', "0.7 Portions Coffee"
    )
    coffee = [p for p in parse_diary(html, DAY).products if p.name == "Coffee"]
    assert len(coffee) == 1
    assert coffee[0].amount == "0.7 Portions"
    assert coffee[0].link is None
    assert coffee[0].time is None  # this synthetic row has no time span


def test_as_dict(normal):
    data = normal.as_dict()
    assert data["day"] == "2026-10-07"
    assert data["calories"] == 363
    assert data["sugar"] == 31.4
    assert len(data["products"]) == 4
    assert data["products"][0] == {
        "name": "Oatmeal",
        "amount": "150 g",
        "calories": 146.0,
        "fat": 2.5,
        "carbs": 246.2,
        "protein": 5.1,
        "link": "/db/en/food/test/oatmeal/index.html",
        "time": "08:15",
    }
    assert data["products"][3]["amount"] is None
    assert data["products"][3]["time"] is None


def test_as_dict_without_products(normal):
    data = normal.as_dict(with_products=False)
    assert "products" not in data
    assert data["day"] == "2026-10-07"
    assert data["fibre"] == 6.2


def test_amount_split_only_when_text_starts_with_a_quantity():
    from custom_components.fddb.parser import _AMOUNT

    assert _AMOUNT.match("150 g Pizza").groups() == ("150 g", "Pizza")
    assert _AMOUNT.match("1 Scoop Impact Whey Protein, Cookies & Cream").groups() == (
        "1 Scoop",
        "Impact Whey Protein, Cookies & Cream",
    )
    assert _AMOUNT.match("0.5 Portion Salat").groups() == ("0.5 Portion", "Salat")
    assert _AMOUNT.match("Bio Apfel Saft") is None


def test_unexpected_failure_inside_the_parser_becomes_a_parse_error(normal_html, monkeypatch):
    # fddb-exporter 2.5.0: never let an unchecked failure escape, report it as a parse error.
    def boom(_cells):
        raise AttributeError("layout changed")

    monkeypatch.setattr(parser_module, "_parse_product", boom)
    with pytest.raises(FddbParseError, match="layout changed"):
        parse_diary(normal_html, date(2026, 10, 7))


def test_totals_are_found_by_label_not_by_position(normal_html):
    # fddb.info dropped a block above the diary in August 2026, which shifted every absolute
    # path (fddb-exporter 2.4.0). Extra blocks before or after the tables must not matter.
    shifted = normal_html.replace(
        '<div class="quicklinks">',
        '<div class="notice"><table><tr><td>Note</td><td>Hello</td></tr></table></div>'
        '<div class="quicklinks">',
    )
    diary = parse_diary(shifted, date(2026, 10, 7))
    assert diary.sugar == 31.4
    assert diary.fibre == 6.2


def test_diary_page_has_no_goal_and_the_action_response_is_unchanged(normal):
    assert not hasattr(normal, "calorie_goal")
    assert "calorie_goal" not in normal.as_dict()


# --- profile / settings page (#4, #10) -----------------------------------------------------
# profile_en.html has the structure of the real English settings page; all values are invented.


@pytest.fixture
def profile_html(load_fixture) -> str:
    return load_fixture("profile_en.html")


@pytest.fixture
def profile(profile_html) -> Profile:
    return parse_profile(profile_html)


def test_profile_values(profile):
    assert profile.as_dict() == {
        "height_cm": 172.0,
        "weight_kg": 64.5,
        "bmi": 22.0,
        "bmi_category": "Normal",
        "occupation": "easy - Example: Student, ...",
        "sports": "no sports",
        "goal": "Not specified",
        "activity_index": 60.0,
        "calorie_goal": 2000.0,
    }


def test_profile_has_no_personal_fields(profile):
    # name, user name, birthday, gender, country and e-mail settings are never read
    assert set(profile.as_dict()) == {
        "height_cm",
        "weight_kg",
        "bmi",
        "bmi_category",
        "occupation",
        "sports",
        "goal",
        "activity_index",
        "calorie_goal",
    }
    assert "Max" not in repr(profile)
    assert "testuser" not in repr(profile)


def test_required_calories_prefer_kcal_over_kilojoules(profile_html):
    # kJ and kcal disagree on purpose: the kcal figure wins
    html = profile_html.replace("8368 kJ", "9999 kJ")
    assert parse_profile(html).calorie_goal == 2000.0


def test_required_calories_fall_back_to_kilojoules(profile_html):
    html = profile_html.replace("&nbsp;<span>(2000 kcal)</span>", "")
    assert parse_profile(html).calorie_goal == 2000.0  # 8368 kJ / 4.184


def test_required_calories_with_kcal_first_and_thousands_separator(profile_html):
    html = profile_html.replace(
        "<b>8368 kJ</b>&nbsp;<span>(2000 kcal)</span>",
        "<b>2,000 kcal</b>&nbsp;<span>(8368 kJ)</span>",
    )
    assert parse_profile(html).calorie_goal == 2000.0


@pytest.mark.parametrize("value", ["0 kcal", "no value", ""])
def test_zero_or_unreadable_required_calories_mean_no_goal(profile_html, value):
    html = profile_html.replace("<b>8368 kJ</b>&nbsp;<span>(2000 kcal)</span>", f"<b>{value}</b>")
    assert parse_profile(html).calorie_goal is None


def test_rows_are_found_by_label_not_by_position(profile_html):
    # swap the "Required" and "Activity" rows
    rows = profile_html.split("\n")
    i = next(n for n, line in enumerate(rows) if "<b>Required</b>" in line)
    rows[i], rows[i + 1] = rows[i + 1], rows[i]
    profile = parse_profile("\n".join(rows))
    assert profile.calorie_goal == 2000.0
    assert profile.activity_index == 60.0


def test_missing_label_gives_none_and_a_debug_log(profile_html, caplog):
    html = profile_html.replace("Sports:", "Fitness:")
    with caplog.at_level("DEBUG", logger=parser_module.__name__):
        profile = parse_profile(html)
    assert profile.sports is None
    assert profile.height_cm == 172.0
    assert "sports" in caplog.text


def test_changed_value_formats_do_not_crash(profile_html):
    html = profile_html.replace("<b>172 cm</b>", "<b>unknown</b>").replace("<b>60%</b>", "<b></b>")
    profile = parse_profile(html)
    assert profile.height_cm is None
    assert profile.activity_index is None
    assert profile.weight_kg == 64.5


def test_bmi_without_category_line(profile_html):
    html = profile_html.replace('<span style="color:#22AA22;">Normal</span><br>', "")
    profile = parse_profile(html)
    assert profile.bmi == 22.0
    assert profile.bmi_category is None


def test_decimal_comma_weight(profile_html):
    assert parse_profile(profile_html.replace("64.5 kg", "64,5 kg")).weight_kg == 64.5


def test_profile_page_while_logged_out(load_fixture):
    with pytest.raises(FddbAuthError):
        parse_profile(load_fixture("diary_logged_out.html"))


@pytest.mark.parametrize("html", ["", "<html><body><p>Maintenance</p></body></html>"])
def test_page_without_any_profile_label_is_a_parse_error(html):
    with pytest.raises(FddbParseError):
        parse_profile(html)


def test_profile_round_trip_and_damaged_store(profile):
    assert Profile.from_dict(profile.as_dict()) == profile
    damaged = Profile.from_dict({"height_cm": "tall", "sports": 5, "weight_kg": True, "x": 1})
    assert damaged == Profile()
    assert Profile.from_dict(None) == Profile()
