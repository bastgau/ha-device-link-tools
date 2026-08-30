"""Test the config entry diagnostics."""

from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.loader import async_get_integration
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN, SOLAR_POWER, async_link

pytestmark = pytest.mark.usefixtures("config_entry")


async def _async_get_diagnostics(hass: HomeAssistant, config_entry: MockConfigEntry) -> dict[str, Any]:
    """Load the diagnostics platform the way Home Assistant does and call it."""
    integration = await async_get_integration(hass, DOMAIN)
    platform = await integration.async_get_platform("diagnostics")
    result: Any = await platform.async_get_config_entry_diagnostics(hass, config_entry)
    return result


async def test_diagnostics_of_an_unlinked_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test diagnostics of an entry that has no recorded link."""
    diagnostics = await _async_get_diagnostics(hass, config_entry)

    assert diagnostics["links"] == {}
    assert diagnostics["entry_options"] == dict(config_entry.options)


@pytest.mark.usefixtures("entity_entry")
async def test_diagnostics_of_a_recorded_link(
    hass: HomeAssistant, config_entry: MockConfigEntry, device: dr.DeviceEntry
) -> None:
    """Test diagnostics report a recorded link and its current registry state."""
    await async_link(hass, SOLAR_POWER, device)

    diagnostics = await _async_get_diagnostics(hass, config_entry)

    assert diagnostics["links"] == {
        SOLAR_POWER: {
            "recorded_identifiers": [["mqtt", "8848_5"]],
            "registered": True,
            "current_device_id": device.id,
        }
    }


@pytest.mark.usefixtures("entity_entry")
async def test_diagnostics_report_a_stale_link(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test diagnostics show a recorded link whose entity is no longer linked to it."""
    await async_link(hass, SOLAR_POWER, device)
    entity_registry.async_update_entity(SOLAR_POWER, device_id=None)

    diagnostics = await _async_get_diagnostics(hass, config_entry)

    assert diagnostics["links"][SOLAR_POWER]["current_device_id"] is None
