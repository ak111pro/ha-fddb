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


# --- further nutrients of the diary page (#8) ------------------------------------------------


@pytest.fixture
def full(load_fixture) -> DiaryDay:
    """The page layout of fddb.info: summary table, then the vitamin and mineral tables."""
    return parse_diary(load_fixture("diary_full.html"), DAY)


def test_full_page_still_has_the_regular_totals(full, normal):
    for key in ("calories", "fat", "carbs", "sugar", "protein", "fibre"):
        assert getattr(full, key) == getattr(normal, key)
    assert len(full.products) == 4


def test_further_macros_by_label(full):
    assert full.nutrients["alcohol"] == 2.5
    assert full.nutrients["cholesterol"] == 45
    assert full.nutrients["salt"] == 3.2154  # from the "Minerals" table, in grams


def test_bread_units_come_from_the_carbohydrate_total(full):
    assert full.nutrients["bread_units"] == 22.5  # "270.0 g (22.5 BE)" in the footer


def test_bread_units_fall_back_to_carbs_over_12(normal_html):
    html = normal_html.replace("<span>(22.5 BE)</span>", "")
    assert parse_diary(html, DAY).nutrients["bread_units"] == 22.5  # 270 g / 12 g


def test_page_without_the_extra_rows_only_has_bread_units(normal):
    assert set(normal.nutrients) == {"bread_units"}
    assert normal.nutrient("alcohol") is None


def test_nutrient_is_zero_on_a_day_without_entries(load_fixture):
    empty = parse_diary(load_fixture("diary_empty.html"), DAY)
    assert empty.nutrients == {}
    assert empty.nutrient("alcohol") == 0.0
    assert empty.nutrient("bread_units") == 0.0


@pytest.mark.parametrize(
    ("text", "target", "expected"),
    [
        ("2.5 g", "g", 2.5),
        ("0.0182 mg", "mg", 0.0182),
        ("1,250 mg", "mg", 1250),
        ("0.5 g", "mg", 500),
        ("2.5192 μg", "ug", 2.5192),  # Greek mu, as FDDB writes it
        ("2.5 µg", "ug", 2.5),  # micro sign
        ("0.0326 mg", "ug", 32.6),
        ("0.179 mg", "ug", 179),
        ("0.4 litres", "l", 0.4),
        ("250 ml", "l", 0.25),
        ("5 mg", "l", None),  # wrong kind of unit
        ("5 litres", "mg", None),
        ("5", "mg", None),  # no unit
        ("5 stone", "mg", None),
        ("n/a", "mg", None),
        ("", "g", None),
    ],
)
def test_unit_conversion(text, target, expected):
    assert parser_module._convert(text, target) == expected


def test_unreadable_extra_value_is_skipped_not_fatal(load_fixture):
    html = load_fixture("diary_full.html").replace('bold;">2.5 g<', 'bold;">lots<')
    diary = parse_diary(html, DAY)
    assert "alcohol" not in diary.nutrients
    assert diary.nutrients["cholesterol"] == 45
    assert diary.sugar == 31.4


def test_value_in_another_unit_is_converted(load_fixture):
    html = load_fixture("diary_full.html").replace("45 mg", "0.045 g")
    assert parse_diary(html, DAY).nutrients["cholesterol"] == 45


def test_first_match_of_a_label_wins_and_product_rows_are_ignored(load_fixture):
    html = load_fixture("diary_full.html").replace(
        '<a href="/db/en/food/test/coffee/index.html">Coffee</a>',
        '<a href="/db/en/food/test/coffee/index.html">Alcohol</a>',
    )
    assert parse_diary(html, DAY).nutrients["alcohol"] == 2.5


def test_nutrients_in_as_dict(full):
    data = full.as_dict()
    assert data["nutrients"]["alcohol"] == 2.5
    assert full.as_dict(with_products=False)["nutrients"]["salt"] == 3.2154


# --- vitamins and minerals (#9) --------------------------------------------------------------

VITAMINS_AND_MINERALS = {
    # key: (value on the page in the fixture, expected in the unit of the key)
    "vitamin_c": 12.5,  # mg
    "retinol": 52.5,  # page: 0.0525 mg, key is in µg
    "vitamin_d": 1.8,  # µg
    "vitamin_e": 2.4,
    "thiamine": 0.314,
    "riboflavin": 0.5,
    "vitamin_b6": 0.45,
    "vitamin_b12": 1.25,  # µg
    "iron": 4.2,
    "zinc": 3.1,
    "magnesium": 98.6,
    "manganese": 1.2,
    "fluorine": 0.1,
    "chlorine": 1500.5,
    "copper": 0.4,
    "potassium": 812.3,
    "calcium": 215,
    "phosphorus": 410.8,
    "sulphur": 120,
    "iodine": 15.2,  # page: 0.0152 mg, key is in µg
}


def test_all_vitamins_and_minerals_are_read(full):
    for key, expected in VITAMINS_AND_MINERALS.items():
        assert full.nutrients[key] == pytest.approx(expected), key


def test_every_known_nutrient_is_covered_by_the_fixture(full):
    assert set(parser_module.NUTRIENTS) == set(VITAMINS_AND_MINERALS) | {
        "alcohol",
        "cholesterol",
        "salt",
        "water",
    }


def test_vitamin_d_in_either_unit(load_fixture):
    # FDDB writes the same nutrient in µg one day and in mg the next.
    html = load_fixture("diary_full.html").replace("<b>1.8 μg</b>", "<b>0.0326 mg</b>")
    assert parse_diary(html, DAY).nutrients["vitamin_d"] == pytest.approx(32.6)


def test_missing_vitamin_table_leaves_those_values_out(load_fixture):
    html = load_fixture("diary_full.html")
    start = html.index("<h3>Vitamins</h3>")
    end = html.index("<p></p><h3>Minerals</h3>")
    diary = parse_diary(html[:start] + html[end:], DAY)
    assert "vitamin_c" not in diary.nutrients
    assert diary.nutrients["iron"] == 4.2
    assert diary.nutrients["alcohol"] == 2.5


def test_zero_is_a_value(load_fixture):
    html = load_fixture("diary_full.html").replace("<b>0.1 mg</b>", "<b>0 mg</b>")
    assert parse_diary(html, DAY).nutrients["fluorine"] == 0.0


# --- water (#7) ------------------------------------------------------------------------------


def test_water_is_the_content_of_foods_and_drinks_in_litres(full):
    assert full.nutrients["water"] == 0.6
    assert parser_module.NUTRIENTS["water"] == ("Water", "l")


def test_water_in_millilitres_is_converted(load_fixture):
    html = load_fixture("diary_full.html").replace("0.6 litres", "250 ml")
    assert parse_diary(html, DAY).nutrients["water"] == 0.25


def test_water_row_is_optional(normal):
    assert "water" not in normal.nutrients


# --- energy balance (#14) --------------------------------------------------------------------


@pytest.fixture
def meals_html(load_fixture) -> str:
    return load_fixture("diary_meals.html")


def test_balance_surplus_is_positive(meals_html):
    # "You consumed 586 kJ (140 kcal) more energy than you require"
    assert parse_diary(meals_html, DAY).balance == 140.0


def test_balance_deficit_is_negative(meals_html):
    html = meals_html.replace("<b>more energy</b>", "<b>less energy</b>")
    assert parse_diary(html, DAY).balance == -140.0


def test_balance_without_kcal_uses_kilojoules(meals_html):
    html = meals_html.replace("(140 kcal)", "")
    assert parse_diary(html, DAY).balance == round(586 / parser_module.KJ_PER_KCAL)


def test_balance_with_thousands_separator(meals_html):
    html = meals_html.replace("(140 kcal)", "(1,140 kcal)")
    assert parse_diary(html, DAY).balance == 1140.0


@pytest.mark.parametrize(
    "replacement",
    [
        "You consumed exactly what you require",  # no direction word
        "You consumed <b>more energy</b> than you require",  # no number
        "",
    ],
)
def test_unreadable_balance_is_none(meals_html, replacement):
    start = meals_html.index("You consumed")
    end = meals_html.index("</div>", start)
    assert parse_diary(meals_html[:start] + replacement + meals_html[end:], DAY).balance is None


def test_page_without_balance_block_gives_none(normal, load_fixture):
    assert normal.balance is None
    assert parse_diary(load_fixture("diary_empty.html"), DAY).balance is None


def test_balance_on_a_day_without_a_product_table(meals_html):
    start = meals_html.index('<table class="myday-table-std"')
    end = meals_html.index("</table>", start) + len("</table>")
    diary = parse_diary(meals_html[:start] + meals_html[end:], DAY)
    assert diary.balance == 140.0
    assert diary.products == []


def test_balance_is_in_the_get_diary_data(meals_html):
    assert parse_diary(meals_html, DAY).as_dict()["balance"] == 140.0
