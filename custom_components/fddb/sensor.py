"""Sensors for FDDB."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FddbConfigEntry
from .coordinator import FddbCoordinator, FddbData
from .entity import FddbEntity
from .periods import day_start, month_start, week_start


def _macro_share(data: FddbData, macro: str) -> float:
    return data.today.macro_share(macro)


@dataclass(frozen=True, kw_only=True)
class FddbSensorDescription(SensorEntityDescription):
    """Describes an FDDB sensor."""

    value_fn: Callable[[FddbData, FddbCoordinator], float | int | datetime | None]
    attributes_fn: Callable[[FddbData, FddbCoordinator], dict[str, Any]] | None = None
    # Only for state class TOTAL: the moment the value started counting from zero.
    last_reset_fn: Callable[[date], datetime] | None = None


# Values that start at zero at the beginning of a period (day, week, month) use state class
# TOTAL with last_reset. TOTAL_INCREASING would be wrong because a value also goes down when
# a diary entry is deleted, and MEASUREMENT is not allowed together with the energy device class.


def _grams(key: str) -> FddbSensorDescription:
    return FddbSensorDescription(
        key=key,
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.TOTAL,
        last_reset_fn=day_start,
        suggested_display_precision=1,
        value_fn=lambda data, _c, key=key: getattr(data.today, key),
    )


def _kcal_total(
    key: str,
    value_fn: Callable[[FddbData, FddbCoordinator], float | None],
    last_reset_fn: Callable[[date], datetime],
    **kwargs: Any,
) -> FddbSensorDescription:
    return FddbSensorDescription(
        key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        state_class=SensorStateClass.TOTAL,
        last_reset_fn=last_reset_fn,
        suggested_display_precision=0,
        value_fn=value_fn,
        **kwargs,
    )


def _kcal_measurement(
    key: str, value_fn: Callable[[FddbData, FddbCoordinator], float | None]
) -> FddbSensorDescription:
    # Averages, yesterday and the remaining budget are snapshots, not sums that start at zero,
    # so they keep the measurement state class and have no device class.
    return FddbSensorDescription(
        key=key,
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=value_fn,
    )


def _remaining(data: FddbData, coordinator: FddbCoordinator) -> float | None:
    goal, _source = coordinator.effective_goal
    if not goal:
        return None
    return round(goal - data.today.calories, 1)


def _goal_percent(data: FddbData, coordinator: FddbCoordinator) -> float | None:
    goal, _source = coordinator.effective_goal
    if not goal:
        return None
    return round(data.today.calories / goal * 100, 1)


SENSORS: tuple[FddbSensorDescription, ...] = (
    _kcal_total(
        "calories",
        lambda data, _c: data.today.calories,
        day_start,
        attributes_fn=lambda data, _c: {"products": data.today.product_attributes()},
    ),
    _grams("fat"),
    _grams("carbs"),
    _grams("sugar"),
    _grams("protein"),
    _grams("fibre"),
    FddbSensorDescription(
        key="products",
        state_class=SensorStateClass.TOTAL,
        last_reset_fn=day_start,
        suggested_display_precision=0,
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
    _kcal_measurement("calories_yesterday", lambda data, _c: data.yesterday_calories),
    _kcal_total("calories_week", lambda data, _c: data.week_calories, week_start),
    _kcal_total("calories_month", lambda data, _c: data.month_calories, month_start),
    _kcal_measurement("calories_avg_7d", lambda data, _c: data.avg_7_days),
    _kcal_measurement("calories_avg_30d", lambda data, _c: data.avg_30_days),
    FddbSensorDescription(
        key="streak",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda data, _c: data.streak,
    ),
    # The goal as FDDB reports it. No device class: energy does not allow state class
    # measurement, and a goal is a setting rather than an accumulating total.
    _kcal_measurement("goal_fddb", lambda _data, coordinator: coordinator.fddb_goal),
    _kcal_measurement("calories_remaining", _remaining),
    FddbSensorDescription(
        key="goal_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_goal_percent,
        attributes_fn=lambda _data, coordinator: {"goal_source": coordinator.effective_goal[1]},
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

    # The product list is only useful as a live attribute (templates, cards). Keeping it out of
    # the recorder avoids the 16 KB attribute limit and a database row per change.
    _unrecorded_attributes = frozenset({"products"})

    def __init__(self, coordinator: FddbCoordinator, description: FddbSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data, self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if (attributes_fn := self.entity_description.attributes_fn) is None:
            return None
        return attributes_fn(self.coordinator.data, self.coordinator)

    @property
    def last_reset(self) -> datetime | None:
        if (last_reset_fn := self.entity_description.last_reset_fn) is None:
            return None
        return last_reset_fn(self.coordinator.data.today.day)
