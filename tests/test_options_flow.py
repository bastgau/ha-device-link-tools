"""Test managing the recorded links from the options flow."""

# pyright: reportOptionalMemberAccess=false

from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from tests.testing_config.common import MockConfigEntry

from .conftest import GRID_IMPORT, LINKS, SOLAR_POWER, async_link

pytestmark = pytest.mark.usefixtures("config_entry")


async def _async_menu(hass: HomeAssistant, config_entry: MockConfigEntry) -> str:
    """Open the options flow and return its flow id."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"add_link", "remove_link"}  # pyright: ignore[reportArgumentType]
    return result["flow_id"]


def _async_offered_entities(result: Any) -> list[str]:
    """Return the entities the add form's picker offers."""
    schema = result["data_schema"].schema
    selector = schema["entity_id"]
    return sorted(selector.config["include_entities"])


async def _async_add_link_form(hass: HomeAssistant, config_entry: MockConfigEntry) -> str:
    """Open the options flow on the add step and return its flow id."""
    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_link"
    return flow_id


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test linking several entities to a picked device."""
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id,
        {"entity_id": [SOLAR_POWER, GRID_IMPORT], "device_id": device.id},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert entity_registry.async_get(GRID_IMPORT).device_id == device.id
    assert config_entry.options[LINKS] == {
        GRID_IMPORT: [["mqtt", "8848_5"]],
        SOLAR_POWER: [["mqtt", "8848_5"]],
    }


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_rejects_an_unknown_device(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test the form reports a device that does not exist."""
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": "does-not-exist"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "device_id_unknown"}


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_rejects_an_entity_deregistered_since_the_form(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the form reports an entity the picker offered and that is gone since.

    The picker only offers registered entities, so this is the one way the add step can
    still be handed an unregistered one.
    """
    flow_id = await _async_add_link_form(hass, config_entry)
    entity_registry.async_remove(SOLAR_POWER)

    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": device.id}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "entity_not_registered"}


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test unlinking an entity from the options flow."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "remove_link"

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": [SOLAR_POWER]})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entity_registry.async_get(SOLAR_POWER).device_id is None
    assert config_entry.options[LINKS] == {}


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_without_selection(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test the remove step re-shows the form when nothing is selected."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": []})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "remove_link"
    assert result["errors"] == {"base": "no_entity_selected"}


async def test_remove_link_without_links(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test the remove step aborts when nothing is linked."""
    flow_id = await _async_menu(hass, config_entry)

    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_links"


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_moves_a_link_we_recorded(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    other_device: dr.DeviceEntry,
) -> None:
    """Test a link recorded here is re-pointed from the form in one go."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_add_link_form(hass, config_entry)
    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": other_device.id}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entity_registry.async_get(SOLAR_POWER).device_id == other_device.id
    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "9000_1"]]}


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link_lists_only_linkable_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the picker offers unlinked entities and the ones recorded here only."""
    entity_registry.async_update_entity(GRID_IMPORT, device_id=device.id)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    assert _async_offered_entities(result) == [SOLAR_POWER]


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link_lists_an_entity_it_linked_itself(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test an entity linked from here stays in the picker, so it can be re-pointed."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    assert _async_offered_entities(result) == [GRID_IMPORT, SOLAR_POWER]


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_without_linkable_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the add step aborts when every entity is linked by its own integration."""
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_linkable_entities"


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_refuses_an_already_linked_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    other_device: dr.DeviceEntry,
) -> None:
    """Test the form reports an entity linked by something other than us.

    The picker leaves such an entity out, so the refusal is reached by its own
    integration claiming it while the form was being filled in.
    """
    flow_id = await _async_add_link_form(hass, config_entry)
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": other_device.id}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "link_set_elsewhere"}
    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
