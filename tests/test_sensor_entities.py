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
