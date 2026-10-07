"""Daily calorie goal for FDDB."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FddbConfigEntry
from .coordinator import FddbCoordinator
from .entity import FddbEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FddbConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FddbGoalNumber(entry.runtime_data)])


class FddbGoalNumber(FddbEntity, NumberEntity):
    """The daily calorie goal (0 = no goal). Stored by the integration."""

    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 10
    _attr_native_unit_of_measurement = "kcal"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: FddbCoordinator) -> None:
        super().__init__(coordinator, "goal")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.goal

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_goal(value or None)
