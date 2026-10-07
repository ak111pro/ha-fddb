"""Problem indicator for FDDB."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    async_add_entities([FddbProblemSensor(entry.runtime_data)])


class FddbProblemSensor(FddbEntity, BinarySensorEntity):
    """On when the last update failed (login, connection or a changed website)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FddbCoordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return not self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        error = self.coordinator.last_exception
        return {"error": str(error) if error and not self.coordinator.last_update_success else None}
