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
    UnitOfInformation,
    UnitOfLength,
    UnitOfMass,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FddbConfigEntry
from .coordinator import FddbCoordinator, FddbData
from .entity import FddbEntity
from .parser import MEALS, OTHER_MEAL
from .periods import day_start, month_start, week_start


def _macro_share(data: FddbData, macro: str) -> float:
    return data.today.macro_share(macro)


@dataclass(frozen=True, kw_only=True)
class FddbSensorDescription(SensorEntityDescription):
    """Describes an FDDB sensor."""

    value_fn: Callable[[FddbData, FddbCoordinator], float | int | str | datetime | None]
    attributes_fn: Callable[[FddbData, FddbCoordinator], dict[str, Any]] | None = None
    # Only for state class TOTAL: the moment the value started counting from zero.
    last_reset_fn: Callable[[date], datetime] | None = None
    # Diagnostics about the fetching itself stay available while a fetch fails; everything else
    # becomes unavailable together with the failed update.
    always_available: bool = False


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


# key, unit, display precision. Vitamin D, retinol, B12 and iodine are in micrograms (FDDB writes
# them in µg or mg depending on the size of the value, the parser converts), all others in mg.
MICRONUTRIENTS: tuple[tuple[str, str, int], ...] = (
    ("vitamin_c", UnitOfMass.MILLIGRAMS, 1),
    ("retinol", UnitOfMass.MICROGRAMS, 0),
    ("vitamin_d", UnitOfMass.MICROGRAMS, 1),
    ("vitamin_e", UnitOfMass.MILLIGRAMS, 1),
    ("thiamine", UnitOfMass.MILLIGRAMS, 2),
    ("riboflavin", UnitOfMass.MILLIGRAMS, 2),
    ("vitamin_b6", UnitOfMass.MILLIGRAMS, 2),
    ("vitamin_b12", UnitOfMass.MICROGRAMS, 1),
    ("iron", UnitOfMass.MILLIGRAMS, 1),
    ("zinc", UnitOfMass.MILLIGRAMS, 1),
    ("magnesium", UnitOfMass.MILLIGRAMS, 0),
    ("manganese", UnitOfMass.MILLIGRAMS, 2),
    ("fluorine", UnitOfMass.MILLIGRAMS, 2),
    ("chlorine", UnitOfMass.MILLIGRAMS, 0),
    ("copper", UnitOfMass.MILLIGRAMS, 2),
    ("potassium", UnitOfMass.MILLIGRAMS, 0),
    ("calcium", UnitOfMass.MILLIGRAMS, 0),
    ("phosphorus", UnitOfMass.MILLIGRAMS, 0),
    ("sulphur", UnitOfMass.MILLIGRAMS, 0),
    ("iodine", UnitOfMass.MICROGRAMS, 0),
)


def _nutrient(
    key: str,
    unit: str | None = UnitOfMass.GRAMS,
    *,
    precision: int = 1,
    device_class: SensorDeviceClass | None = SensorDeviceClass.WEIGHT,
    enabled: bool = True,
) -> FddbSensorDescription:
    """A per-day value that only some diary pages show (alcohol, salt, vitamins, ...).

    Same state class pattern as the macros. ``unit`` is the unit the parser converts to.
    """
    return FddbSensorDescription(
        key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.TOTAL,
        last_reset_fn=day_start,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        value_fn=lambda data, _c, key=key: data.today.nutrient(key),
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
    key: str,
    value_fn: Callable[[FddbData, FddbCoordinator], float | None],
    **kwargs: Any,
) -> FddbSensorDescription:
    # Averages, yesterday and the remaining budget are snapshots, not sums that start at zero,
    # so they keep the measurement state class and have no device class.
    return FddbSensorDescription(
        key=key,
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=value_fn,
        **kwargs,
    )


def _meal_calories(data: FddbData, key: str) -> float | None:
    """Energy of one meal today: 0 for a meal without entries on a grouped day, else unknown."""
    meals = data.today.meals
    if not meals:
        return None
    return meals[key].calories if key in meals else 0.0


def _meal_attributes(data: FddbData, key: str) -> dict[str, Any]:
    meals = data.today.meals
    meal = meals.get(key) if meals else None
    if meals and meal is None:
        return {"fat": 0.0, "carbs": 0.0, "protein": 0.0}
    return {
        "fat": meal.fat if meal else None,
        "carbs": meal.carbs if meal else None,
        "protein": meal.protein if meal else None,
    }


def _meal_sensor(key: str) -> FddbSensorDescription:
    """Calories of one meal group today (same pattern as the daily total, with its macros)."""
    return _kcal_total(
        f"calories_{key}",
        lambda data, _c, key=key: _meal_calories(data, key),
        day_start,
        attributes_fn=lambda data, _c, key=key: _meal_attributes(data, key),
        # Only for a group with a name outside of MEALS, so off unless needed.
        entity_registry_enabled_default=key != OTHER_MEAL,
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


def _profile_value(coordinator: FddbCoordinator, name: str) -> float | str | None:
    """One value of the stored FDDB profile, None until the profile was read."""
    return getattr(coordinator.profile, name, None)


def _occupation_level(coordinator: FddbCoordinator) -> str | None:
    """ "easy" from FDDB's "easy - Example: Student, ...": the level without the examples."""
    text = _profile_value(coordinator, "occupation")
    if not isinstance(text, str):
        return None
    return text.split(" - ", 1)[0].strip() or None


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
    # --- further values of the diary page. The useful ones are on by default ----------------
    _nutrient("alcohol"),
    # Bread units have no device class; FDDB shows 1 BE per 12 g of carbohydrates.
    _nutrient("bread_units", "BE", device_class=None),
    _nutrient("cholesterol", UnitOfMass.MILLIGRAMS, enabled=False),
    # The water content of the logged foods and drinks (FDDB's "Water" row), NOT the drinking
    # intake: FDDB has no water intake or water goal.
    _nutrient(
        "water",
        UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME,
        enabled=False,
    ),
    _nutrient("salt", precision=2),
    # --- vitamins and minerals, all disabled by default to keep the entity list short -------
    # unit and display precision: (mg, 1) means the parser converts to mg, shown with 1 decimal
    *(
        _nutrient(key, unit, precision=precision, enabled=False)
        for key, unit, precision in MICRONUTRIENTS
    ),
    # --- calories per meal group (accounts with "Grouping: By meals") -----------------------
    *(_meal_sensor(key) for key in (*MEALS, OTHER_MEAL)),
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
    # FDDB's energy balance of the day: consumed minus required (with activities), so positive is
    # a surplus. A signed snapshot, so measurement and no device class.
    _kcal_measurement("balance", lambda data, _c: data.today.balance),
    _kcal_measurement("balance_yesterday", lambda data, _c: data.yesterday_balance),
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
    # The goal as FDDB reports it for today: the required energy of the diary page, else the
    # value of the settings page. No device class: energy does not allow state class
    # measurement, and a goal is a setting rather than an accumulating total.
    _kcal_measurement(
        "goal_fddb",
        lambda _data, coordinator: coordinator.fddb_goal_today[0],
        attributes_fn=lambda _data, coordinator: {"goal_source": coordinator.fddb_goal_today[1]},
    ),
    _kcal_measurement("calories_remaining", _remaining),
    FddbSensorDescription(
        key="goal_progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_goal_percent,
        attributes_fn=lambda _data, coordinator: {"goal_source": coordinator.effective_goal[1]},
    ),
    # --- profile (read from the FDDB settings page every few hours) -------------------------
    FddbSensorDescription(
        key="height",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "height_cm"),
    ),
    FddbSensorDescription(
        key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "weight_kg"),
    ),
    FddbSensorDescription(
        key="bmi",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "bmi"),
        attributes_fn=lambda _data, coordinator: {
            "category": _profile_value(coordinator, "bmi_category")
        },
    ),
    FddbSensorDescription(
        key="occupation",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, coordinator: _occupation_level(coordinator),
        attributes_fn=lambda _data, coordinator: {
            "description": _profile_value(coordinator, "occupation")
        },
    ),
    FddbSensorDescription(
        key="sports",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "sports"),
    ),
    FddbSensorDescription(
        key="profile_goal",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "goal"),
    ),
    FddbSensorDescription(
        key="activity_index",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda _data, coordinator: _profile_value(coordinator, "activity_index"),
    ),
    # --- diagnostics -------------------------------------------------------------------
    FddbSensorDescription(
        key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda _data, coordinator: coordinator.last_success,
    ),
    FddbSensorDescription(
        key="fetch_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda _data, coordinator: coordinator.last_fetch_duration,
    ),
    FddbSensorDescription(
        key="consecutive_errors",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda _data, coordinator: coordinator.consecutive_errors,
        attributes_fn=lambda _data, coordinator: {
            "last_error": coordinator.last_error,
            "last_error_time": (
                coordinator.last_error_time.isoformat() if coordinator.last_error_time else None
            ),
        },
    ),
    FddbSensorDescription(
        key="total_errors",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda _data, coordinator: coordinator.total_errors,
    ),
    FddbSensorDescription(
        key="storage_size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KILOBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        always_available=True,
        value_fn=lambda _data, coordinator: coordinator.storage_size,
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
    _unrecorded_attributes = frozenset({"products", "last_error", "last_error_time"})

    def __init__(self, coordinator: FddbCoordinator, description: FddbSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return self.entity_description.always_available or super().available

    @property
    def native_value(self) -> float | int | str | datetime | None:
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
