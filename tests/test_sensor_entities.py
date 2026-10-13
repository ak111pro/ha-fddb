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


def _make_sensor(sensor_module, key, load_fixture, goal=None, fddb_goal=None, profile="default"):
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
    )
    coordinator_module = sys.modules["fddb_under_test.coordinator"]
    if profile == "default":
        profile = parser.parse_profile(load_fixture("profile_en.html"))

    class FakeCoordinator(SimpleNamespace):
        # Use the real override logic, not a copy of it.
        effective_goal = coordinator_module.FddbCoordinator.effective_goal

    coordinator = FakeCoordinator(
        data=data,
        goal=goal,
        fddb_goal=fddb_goal,
        profile=profile,
        last_success=datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc),
        last_fetch_duration=1.234,
        consecutive_errors=2,
        total_errors=7,
        last_error="fddb.info answered HTTP 502",
        last_error_time=datetime(2026, 10, 7, 11, 30, tzinfo=timezone.utc),
        storage_size=45678,
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
        if description.key in (
            "calories",
            "goal_progress",
            "consecutive_errors",
            "bmi",
            "occupation",
        ):
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
    "fetch_duration": ("duration", "measurement", "s", None, 2),
    "consecutive_errors": (None, "measurement", None, None, 0),
    "total_errors": (None, "total_increasing", None, None, 0),
    "storage_size": ("data_size", "measurement", "B", None, 1),
    "height": ("distance", "measurement", "cm", None, 0),
    "weight": ("weight", "measurement", "kg", None, 1),
    "bmi": (None, "measurement", None, None, 0),
    "occupation": (None, None, None, None, None),
    "sports": (None, None, None, None, None),
    "profile_goal": (None, None, None, None, None),
    "activity_index": (None, "measurement", "%", None, 0),
}
# Diagnostics about the fetching itself: stay available while a fetch fails.
DIAGNOSTIC = {"last_update", "fetch_duration", "consecutive_errors", "total_errors", "storage_size"}
# Profile values: diagnostic category, but unavailable together with a failed update.
PROFILE_DIAGNOSTIC = {"height", "occupation", "sports", "profile_goal", "activity_index"}


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


# --- diagnostics (#11) -----------------------------------------------------------------------


def test_diagnostic_sensors_are_diagnostic_and_always_available(sensor_module, load_fixture):
    for description in sensor_module.SENSORS:
        is_diagnostic = description.entity_category == "diagnostic"
        assert is_diagnostic == (description.key in DIAGNOSTIC | PROFILE_DIAGNOSTIC), (
            description.key
        )
        sensor = _make_sensor(sensor_module, description.key, load_fixture)
        sensor.coordinator.last_update_success = False  # a failed fetch
        assert sensor.available == (description.key in DIAGNOSTIC), description.key


def test_diagnostic_values(sensor_module, load_fixture):
    def value(key):
        return _make_sensor(sensor_module, key, load_fixture).native_value

    assert value("last_update") == datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    assert value("fetch_duration") == 1.234
    assert value("consecutive_errors") == 2
    assert value("total_errors") == 7
    assert value("storage_size") == 45678


def test_consecutive_errors_carries_the_last_error(sensor_module, load_fixture):
    sensor = _make_sensor(sensor_module, "consecutive_errors", load_fixture)
    assert sensor.extra_state_attributes == {
        "last_error": "fddb.info answered HTTP 502",
        "last_error_time": "2026-10-07T11:30:00+00:00",
    }
    # error texts are not worth a recorder row each
    unrecorded = sensor_module.FddbSensor._Entity__combined_unrecorded_attributes
    assert {"last_error", "last_error_time"} <= unrecorded


def test_storage_size_is_shown_in_kilobytes(sensor_module):
    description = next(d for d in sensor_module.SENSORS if d.key == "storage_size")
    assert description.suggested_unit_of_measurement == "kB"


# --- profile sensors (#10) -------------------------------------------------------------------


def test_profile_values(sensor_module, load_fixture):
    def value(key):
        return _make_sensor(sensor_module, key, load_fixture).native_value

    assert value("height") == 172.0
    assert value("weight") == 64.5
    assert value("bmi") == 22.0
    assert value("occupation") == "easy"  # level only, the description is an attribute
    assert value("sports") == "no sports"
    assert value("profile_goal") == "Not specified"
    assert value("activity_index") == 60.0


def test_bmi_and_occupation_attributes(sensor_module, load_fixture):
    bmi = _make_sensor(sensor_module, "bmi", load_fixture)
    assert bmi.extra_state_attributes == {"category": "Normal"}
    occupation = _make_sensor(sensor_module, "occupation", load_fixture)
    assert occupation.extra_state_attributes == {"description": "easy - Example: Student, ..."}


@pytest.mark.parametrize("key", sorted(PROFILE_DIAGNOSTIC | {"weight", "bmi"}))
def test_profile_sensors_are_unknown_before_the_profile_was_read(sensor_module, load_fixture, key):
    sensor = _make_sensor(sensor_module, key, load_fixture, profile=None)
    assert sensor.native_value is None


def test_weight_and_bmi_are_regular_sensors(sensor_module):
    for key in ("weight", "bmi"):
        description = next(d for d in sensor_module.SENSORS if d.key == key)
        assert description.entity_category is None


def test_no_sensor_for_personal_profile_details(sensor_module):
    keys = {d.key for d in sensor_module.SENSORS}
    for personal in ("gender", "birthday", "first_name", "name", "username", "country", "email"):
        assert not any(personal in key for key in keys), personal
