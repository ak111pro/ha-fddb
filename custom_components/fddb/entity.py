"""Base entity for FDDB."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BASE_URL, DOMAIN
from .coordinator import FddbCoordinator


class FddbEntity(CoordinatorEntity[FddbCoordinator]):
    """Common device info and unique ids."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FddbCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=f"FDDB {entry.title}",
            manufacturer="FDDB",
            model="Food diary",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"{BASE_URL}/db/i18n/myday20/",
        )
