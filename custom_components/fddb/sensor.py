"""Sensors for FDDB."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FddbConfigEntry
from .coordinator import FddbCoordinator, FddbData
from .entity import FddbEntity

KCAL = "kcal"
KCAL_PER_GRAM = {"fat": 9.0, "carbs": 4.0, "protein": 4.0}


def _macro_share(data: FddbData, macro: str) -> float | None:
    energy = {key: getattr(data.today, key) * factor for key, factor in KCAL_PER_GRAM.items()}
    total = sum(energy.values())
    return round(energy[macro] / total * 100, 1) if total else None


@dataclass(frozen=True, kw_only=True)
class FddbSensorDescription(SensorEntityDescription):
    """Describes an FDDB sensor."""

    value_fn: Callable[[FddbData, FddbCoordinator], float | int | datetime | None]


def _grams(key: str) -> FddbSensorDescription:
    return FddbSensorDescription(
        key=key,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data, _c, key=key: getattr(data.today, key),
    )


def _remaining(data: FddbData, coordinator: FddbCoordinator) -> float | None:
    if not coordinator.goal:
        return None
    return round(coordinator.goal - data.today.calories, 1)


def _goal_percent(data: FddbData, coordinator: FddbCoordinator) -> float | None:
    if not coordinator.goal:
        return None
    return round(data.today.calories / coordinator.goal * 100, 1)


SENSORS: tuple[FddbSensorDescription, ...] = (
    FddbSensorDescription(
        key="calories",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.today.calories,
    ),
    _grams("fat"),
    _grams("carbs"),
    _grams("sugar"),
    _grams("protein"),
    _grams("fibre"),
    FddbSensorDescription(
        key="products",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, _c: len(data.today.products),
    ),
    *(
        FddbSensorDescription(
            key=f"{macro}_share",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=lambda data, _c, macro=macro: _macro_share(data, macro),
        )
        for macro in ("protein", "carbs", "fat")
    ),
    FddbSensorDescription(
        key="calories_yesterday",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.yesterday_calories,
    ),
    FddbSensorDescription(
        key="calories_week",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.week_calories,
    ),
    FddbSensorDescription(
        key="calories_month",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.month_calories,
    ),
    FddbSensorDescription(
        key="calories_avg_7d",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.avg_7_days,
    ),
    FddbSensorDescription(
        key="calories_avg_30d",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.avg_30_days,
    ),
    FddbSensorDescription(
        key="streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data, _c: data.streak,
    ),
    FddbSensorDescription(
        key="calories_remaining",
        native_unit_of_measurement=KCAL,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_remaining,
    ),
    FddbSensorDescription(
        key="goal_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_goal_percent,
    ),
    FddbSensorDescription(
        key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data, _c: data.last_update,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FddbConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(FddbSensor(coordinator, description) for description in SENSORS)


class FddbSensor(FddbEntity, SensorEntity):
    """An FDDB value."""

    entity_description: FddbSensorDescription

    def __init__(self, coordinator: FddbCoordinator, description: FddbSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data, self.coordinator)
