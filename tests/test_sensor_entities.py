"""Sensor descriptions and entity behaviour.

These need Home Assistant itself. They are skipped when it is not installed (CI only
installs the lightweight parser dependencies) and can be run inside a Home Assistant
container, see the README's development section.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import importlib
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("homeassistant")


@pytest.fixture(scope="module")
def sensor_module(fddb_ha):
    return importlib.import_module(f"{fddb_ha}.sensor")


DAY = date(2026, 10, 7)


def _make_sensor(sensor_module, key, load_fixture, goal=None, fddb_goal=None):
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
    coordinator_module = sys.modules["fddb_under_test.coordinator"]

    class FakeCoordinator(SimpleNamespace):
        # Use the real override logic, not a copy of it.
        effective_goal = coordinator_module.FddbCoordinator.effective_goal

    coordinator = FakeCoordinator(
        data=data,
        goal=goal,
        fddb_goal=fddb_goal,
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
        if description.key in ("calories", "goal_progress"):
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
    "goal_fddb": (None, "measurement", "kcal", None, 0),
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


# today's calories in diary_normal.html: 363 kcal


@pytest.mark.parametrize(
    ("goal", "fddb_goal", "source", "remaining", "progress"),
    [
        (None, None, None, None, None),
        (0, None, None, None, None),
        (2000, None, "manual", 1637.0, 18.1),
        (None, 2400, "fddb", 2037.0, 15.1),
        (0, 2400, "fddb", 2037.0, 15.1),
        (2000, 2400, "manual", 1637.0, 18.1),  # the number entity wins when above 0
    ],
)
def test_goal_override_logic(
    sensor_module, load_fixture, goal, fddb_goal, source, remaining, progress
):
    def state(key):
        sensor = _make_sensor(sensor_module, key, load_fixture, goal=goal, fddb_goal=fddb_goal)
        return sensor.native_value, sensor.extra_state_attributes

    assert state("calories_remaining")[0] == remaining
    value, attributes = state("goal_progress")
    assert value == progress
    assert attributes == {"goal_source": source}


def test_fddb_goal_sensor_reports_the_goal_from_fddb(sensor_module, load_fixture):
    sensor = _make_sensor(sensor_module, "goal_fddb", load_fixture, goal=1800, fddb_goal=2400)
    assert sensor.native_value == 2400  # independent of the manual goal
    assert _make_sensor(sensor_module, "goal_fddb", load_fixture).native_value is None
