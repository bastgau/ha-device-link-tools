"""Diagnostics for the Device Link Tools integration."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .helpers import as_pairs
from .reapply import DeviceLinkToolsConfigEntry, async_stored_links


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DeviceLinkToolsConfigEntry) -> dict[str, Any]:
    """Return the recorded links and their current registry state.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (DeviceLinkToolsConfigEntry): The config entry.

    Returns:
        dict[str, Any]: The diagnostics data.

    """
    entity_registry = er.async_get(hass)
    links = async_stored_links(entry)

    entities: dict[str, Any] = {}
    for entity_id, identifiers in sorted(links.items()):
        registry_entry = entity_registry.async_get(entity_id)
        entities[entity_id] = {
            "recorded_identifiers": as_pairs(identifiers),
            "registered": registry_entry is not None,
            "current_device_id": registry_entry.device_id if registry_entry else None,
        }

    return {
        "entry_options": dict(entry.options),
        "links": entities,
    }
