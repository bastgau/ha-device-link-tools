"""Test reading an entity linked to a pre-migration composite device."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN, SOLAR_POWER


@pytest.mark.parametrize("load_registries", [False])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_read_identifiers_of_composite_device(hass: HomeAssistant, composite_linked_entity: str) -> None:
    """Test a composite id reads as the union of the devices it was split into."""
    entry = MockConfigEntry(domain=DOMAIN, title="Device Link Tools")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "read_identifiers",
        {"entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
    )

    assert response == {
        "entity_id": SOLAR_POWER,
        "device_id": composite_linked_entity,
        "identifiers": [["mqtt", "8848_5"], ["tasmota", "8848"]],
        "connections": [["mac", "aa:bb:cc:dd:ee:ff"]],
        "name": "Boiler",
    }


@pytest.mark.parametrize("load_registries", [False])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_add_identifier_refuses_composite_device_id(hass: HomeAssistant, composite_linked_entity: str) -> None:
    """Test a composite id ca@nnot be picked as the target device."""
    entry = MockConfigEntry(domain=DOMAIN, title="Device Link Tools")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": SOLAR_POWER, "device_id": composite_linked_entity},
            blocking=True,
        )

    assert err.value.translation_key == "device_id_composite"
