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
    """On while updates fail (login, connection or a changed website).

    The other sensors keep their last values meanwhile (see ``FddbCoordinator._fallback``), so
    this follows the error streak rather than ``last_update_success``.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FddbCoordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.consecutive_errors > 0 or not self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"error": self.coordinator.last_error if self.is_on else None}
