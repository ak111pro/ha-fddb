"""The ``products`` attribute of the daily summary sensor."""

from __future__ import annotations

from datetime import date
import json

from conftest import parser

DAY = date(2026, 10, 7)
KEYS = ["name", "amount", "calories", "fat", "carbs", "protein", "link"]


def _parse(load_fixture, name="diary_normal.html"):
    return parser.parse_diary(load_fixture(name), DAY)


def test_attribute_has_the_documented_keys_and_values(load_fixture):
    products = _parse(load_fixture).product_attributes()
    assert len(products) == 4
    assert all(list(p) == KEYS for p in products)
    assert products[0] == {
        "name": "Oatmeal",
        "amount": "150 g",
        "calories": 146.0,
        "fat": 2.5,
        "carbs": 246.2,
        "protein": 5.1,
        "link": "/db/en/food/test/oatmeal/index.html",
    }


def test_link_is_the_relative_path_from_the_page(load_fixture):
    for product in _parse(load_fixture).product_attributes():
        assert product["link"].startswith("/db/")


def test_own_food_has_no_link_and_stays_in_the_list(load_fixture):
    html = load_fixture("diary_normal.html").replace(
        '<a href="/db/en/food/test/coffee/index.html">Coffee</a>', "0.7 Portions Coffee"
    )
    products = parser.parse_diary(html, DAY).product_attributes()
    coffee = [p for p in products if p["name"] == "Coffee"]
    assert coffee == [
        {
            "name": "Coffee",
            "amount": "0.7 Portions",
            "calories": coffee[0]["calories"],
            "fat": coffee[0]["fat"],
            "carbs": coffee[0]["carbs"],
            "protein": coffee[0]["protein"],
            "link": None,
        }
    ]


def test_empty_day_gives_an_empty_list(load_fixture):
    assert _parse(load_fixture, "diary_empty.html").product_attributes() == []


def test_attribute_is_json_serialisable_and_small_for_a_normal_day(load_fixture):
    products = _parse(load_fixture).product_attributes()
    assert len(json.dumps(products)) < 2000
