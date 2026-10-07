"""The FDDB food diary integration."""

from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import FddbClient
from .const import ATTR_CONFIG_ENTRY_ID, ATTR_DATE, DOMAIN, SERVICE_GET_DIARY, SERVICE_REFRESH
from .coordinator import FddbCoordinator, fddb_today
from .parser import FddbError

PLATFORMS = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type FddbConfigEntry = ConfigEntry[FddbCoordinator]

SERVICE_SCHEMA_REFRESH = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})
SERVICE_SCHEMA_GET_DIARY = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_DATE): cv.date,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once for all entries."""

    def _coordinators(call: ServiceCall) -> list[FddbCoordinator]:
        entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED and (entry_id is None or e.entry_id == entry_id)
        ]
        if not entries:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_loaded_entry"
            )
        return [e.runtime_data for e in entries]

    async def handle_refresh(call: ServiceCall) -> None:
        for coordinator in _coordinators(call):
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="refresh_failed",
                    translation_placeholders={"error": str(coordinator.last_exception)},
                )

    async def handle_get_diary(call: ServiceCall) -> ServiceResponse:
        coordinators = _coordinators(call)
        if len(coordinators) > 1:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="multiple_entries"
            )
        day: date = call.data.get(ATTR_DATE) or fddb_today()
        if day > fddb_today():
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="future_date"
            )
        try:
            diary = await coordinators[0].async_get_day(day)
        except FddbError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="refresh_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return diary.as_dict()

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=SERVICE_SCHEMA_REFRESH
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DIARY,
        handle_get_diary,
        schema=SERVICE_SCHEMA_GET_DIARY,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: FddbConfigEntry) -> bool:
    """Set up FDDB from a config entry."""
    client = FddbClient(
        async_create_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = FddbCoordinator(hass, entry, client)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start_background_jobs()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FddbConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
