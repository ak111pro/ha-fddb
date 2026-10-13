"""Diagnostics for FDDB."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import FddbConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "title", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FddbConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "last_exception": str(coordinator.last_exception) if coordinator.last_exception else None,
        "today": data.today.as_dict(with_products=False) if data else None,
        "consecutive_errors": coordinator.consecutive_errors,
        "total_errors": coordinator.total_errors,
        "last_error": coordinator.last_error,
        "last_fetch_duration": coordinator.last_fetch_duration,
        "last_success": coordinator.last_success.isoformat() if coordinator.last_success else None,
        "storage_size": coordinator.storage_size,
        "stored_days": len(coordinator._days),  # noqa: SLF001
    }
