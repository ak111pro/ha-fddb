"""Sensor descriptions and entity behaviour.

These need Home Assistant itself. They are skipped when it is not installed (CI only
installs the lightweight parser dependencies) and can be run inside a Home Assistant
container, see the README's development section.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("homeassistant")

PACKAGE_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "fddb"


@pytest.fixture(scope="module")
def sensor_module():
    """Load the real package (with its Home Assistant imports) under a private name."""
    name = "fddb_under_test"
    spec = importlib.util.spec_from_file_location(
        name, PACKAGE_DIR / "__init__.py", submodule_search_locations=[str(PACKAGE_DIR)]
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    return importlib.import_module(f"{name}.sensor")


DAY = date(2026, 10, 7)


def _make_sensor(sensor_module, key, load_fixture, goal=None):
    parser = sys.modules["fddb_under_test.parser"]
    today = parser.parse_diary(load_fixture("diary_normal.html"), DAY)
    data = SimpleNamespace(
        today=today,
        yesterday_calories=1800.0,
        week_calories=9000.0,
        month_calories=30000.0,
        avg_7_days=2000.0,
        avg_30_days=1900.0,
        streak=3,
        last_update=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
    )
    coordinator = SimpleNamespace(
        data=data,
        goal=goal,
        config_entry=SimpleNamespace(unique_id="user", entry_id="abc", title="user"),
        last_update_success=True,
    )
    description = next(d for d in sensor_module.SENSORS if d.key == key)
    return sensor_module.FddbSensor(coordinator, description)


def test_calories_sensor_exposes_products(sensor_module, load_fixture):
    sensor = _make_sensor(sensor_module, "calories", load_fixture)
    products = sensor.extra_state_attributes["products"]
    assert [p["name"] for p in products][0] == "Oatmeal"
    assert set(products[0]) == {"name", "amount", "calories", "fat", "carbs", "protein", "link"}


def test_products_attribute_is_not_recorded(sensor_module):
    assert "products" in sensor_module.FddbSensor._Entity__combined_unrecorded_attributes


def test_other_sensors_have_no_extra_attributes(sensor_module, load_fixture):
    for description in sensor_module.SENSORS:
        if description.key == "calories":
            continue
        sensor = _make_sensor(sensor_module, description.key, load_fixture)
        assert not sensor.extra_state_attributes, description.key


@pytest.mark.parametrize("key", ["protein_share", "carbs_share", "fat_share"])
def test_share_sensors_report_zero_on_an_empty_day(sensor_module, load_fixture, key):
    sensor = _make_sensor(sensor_module, key, load_fixture)
    sensor.coordinator.data.today = sys.modules["fddb_under_test.parser"].DiaryDay(day=DAY)
    assert sensor.native_value == 0.0


# key: (device class, state class, unit, last_reset kind, display precision)
EXPECTED = {
    "calories": ("energy", "total", "kcal", "day", 0),
    "fat": ("weight", "total", "g", "day", 1),
    "carbs": ("weight", "total", "g", "day", 1),
    "sugar": ("weight", "total", "g", "day", 1),
    "protein": ("weight", "total", "g", "day", 1),
    "fibre": ("weight", "total", "g", "day", 1),
    "products": (None, "total", None, "day", 0),
    "protein_share": (None, "measurement", "%", None, 0),
    "carbs_share": (None, "measurement", "%", None, 0),
    "fat_share": (None, "measurement", "%", None, 0),
    "calories_yesterday": (None, "measurement", "kcal", None, 0),
    "calories_week": ("energy", "total", "kcal", "week", 0),
    "calories_month": ("energy", "total", "kcal", "month", 0),
    "calories_avg_7d": (None, "measurement", "kcal", None, 0),
    "calories_avg_30d": (None, "measurement", "kcal", None, 0),
    "streak": (None, "measurement", "d", None, 0),
    "calories_remaining": (None, "measurement", "kcal", None, 0),
    "goal_progress": (None, "measurement", "%", None, 0),
    "last_update": ("timestamp", None, None, None, None),
}


def test_every_sensor_is_covered(sensor_module):
    assert {d.key for d in sensor_module.SENSORS} == set(EXPECTED)


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_classes_and_units(sensor_module, key):
    description = next(d for d in sensor_module.SENSORS if d.key == key)
    device_class, state_class, unit, _reset, precision = EXPECTED[key]
    assert description.device_class == device_class
    assert description.state_class == state_class
    assert description.native_unit_of_measurement == unit
    assert description.suggested_display_precision == precision


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_combination_is_valid_for_home_assistant(sensor_module, key):
    from homeassistant.components.sensor.const import (
        DEVICE_CLASS_STATE_CLASSES,
        DEVICE_CLASS_UNITS,
    )

    description = next(d for d in sensor_module.SENSORS if d.key == key)
    if description.device_class in DEVICE_CLASS_STATE_CLASSES and description.state_class:
        assert description.state_class in DEVICE_CLASS_STATE_CLASSES[description.device_class]
    if description.device_class in DEVICE_CLASS_UNITS:
        assert (
            description.native_unit_of_measurement in DEVICE_CLASS_UNITS[description.device_class]
        )


@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_last_reset(sensor_module, load_fixture, key):
    kind = EXPECTED[key][3]
    sensor = _make_sensor(sensor_module, key, load_fixture)  # data.today.day = Wed 2026-10-07
    expected = {
        None: None,
        "day": datetime(2026, 10, 7, tzinfo=ZoneInfo("Europe/Berlin")),
        "week": datetime(2026, 10, 5, tzinfo=ZoneInfo("Europe/Berlin")),
        "month": datetime(2026, 10, 1, tzinfo=ZoneInfo("Europe/Berlin")),
    }[kind]
    assert sensor.last_reset == expected
    # last_reset is only valid together with state class total
    assert (sensor.last_reset is not None) == (sensor.state_class == "total")
