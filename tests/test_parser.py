"""Tests for the diary parser, using synthetic HTML fixtures."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.fddb.parser import (
    DiaryDay,
    FddbAuthError,
    FddbParseError,
    parse_diary,
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
        '<tr class="myday-table-std-td-footer">', '<tr class="myday-table-std-td-footer"><td>x</td></tr><tr>'
    )
    # The last row now only has one cell less than required for totals.
    html = html.replace("<td><b>14.1 g</b></td>", "")
    with pytest.raises(FddbParseError, match="totals"):
        parse_diary(html, DAY)


def test_product_row_without_link_raises_parse_error(normal_html):
    html = normal_html.replace(
        '<a href="/db/en/food/test/coffee/index.html">Coffee</a>', "Coffee"
    )
    with pytest.raises(FddbParseError, match="link"):
        parse_diary(html, DAY)


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
