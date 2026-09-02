"""Test managing the recorded links from the options flow."""

# pyright: reportOptionalMemberAccess=false

from typing import Any

import pytest
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN, GRID_IMPORT, LINKS, SOLAR_POWER, async_link

pytestmark = pytest.mark.usefixtures("config_entry")


def _async_menu_options(result: Any) -> set[str]:
    """Return the entries the menu offers."""
    return set(result["menu_options"])


async def _async_menu(hass: HomeAssistant, config_entry: MockConfigEntry) -> str:
    """Open the options flow and return its flow id."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    # The steps with nothing to work on are left out, so only the exit always shows.
    assert "exit" in _async_menu_options(result)
    return result["flow_id"]


def _async_offered_entities(result: Any) -> list[str]:
    """Return the entities the add form's picker offers."""
    schema = result["data_schema"].schema
    selector = schema["entity_id"]
    return sorted(selector.config["include_entities"])


def _async_offered_links(result: Any) -> list[dict[str, str]]:
    """Return the choices the remove form offers, as value/label pairs."""
    selector = result["data_schema"].schema["entity_id"]
    return [dict(option) for option in selector.config["options"]]


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

    assert result["type"] is FlowResultType.MENU
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

    assert result["type"] is FlowResultType.MENU
    assert entity_registry.async_get(SOLAR_POWER).device_id is None
    assert config_entry.options[LINKS] == {}


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_labels_the_device(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test each choice names the entity and the device it is linked to."""
    entity_registry.async_update_entity(SOLAR_POWER, name="Solar power")
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    assert _async_offered_links(result) == [{"value": SOLAR_POWER, "label": "Solar power (Boiler)"}]


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_labels_an_unnamed_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test an entity carrying no name of its own falls back to its entity id."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    assert _async_offered_links(result) == [{"value": SOLAR_POWER, "label": f"{SOLAR_POWER} (Boiler)"}]


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_labels_an_unlinked_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test a recorded link the registry no longer carries stays offered to unlink."""
    await async_link(hass, SOLAR_POWER, device)
    entity_registry.async_update_entity(SOLAR_POWER, device_id=None)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    assert _async_offered_links(result) == [{"value": SOLAR_POWER, "label": SOLAR_POWER}]


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_without_selection(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test ticking nothing leaves the step without unlinking anything."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": []})

    assert result["type"] is FlowResultType.MENU
    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


async def test_remove_link_is_not_offered_without_links(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test the menu leaves the unlink entry out when nothing is linked."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert "remove_link" not in _async_menu_options(result)


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link_rejects_a_link_we_recorded(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
    other_device: dr.DeviceEntry,
) -> None:
    """Test the picker refuses an entity it no longer offers.

    The selector validates a submission against ``include_entities``, so leaving the
    recorded links out of the picker also rules them out of a submission: re-pointing
    one goes through the ``add_identifier`` action.
    """
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_add_link_form(hass, config_entry)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            flow_id, {"entity_id": [SOLAR_POWER], "device_id": other_device.id}
        )


@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_moves_a_link_we_recorded(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    other_device: dr.DeviceEntry,
) -> None:
    """Test the action re-points a recorded link in one call, as the form used to."""
    await async_link(hass, SOLAR_POWER, device)

    await async_link(hass, SOLAR_POWER, other_device)

    assert entity_registry.async_get(SOLAR_POWER).device_id == other_device.id
    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "9000_1"]]}


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link_lists_only_linkable_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the picker offers the entities that are linked to nothing only."""
    entity_registry.async_update_entity(GRID_IMPORT, device_id=device.id)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    assert _async_offered_entities(result) == [SOLAR_POWER]


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_link_omits_an_entity_it_linked_itself(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test a link recorded here leaves the picker, which keeps it short."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    assert _async_offered_entities(result) == [GRID_IMPORT]


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_without_linkable_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the menu leaves the add entry out when every entity is already linked."""
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert _async_menu_options(result) == {"exit"}


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


async def _async_orphan(hass: HomeAssistant, device_registry: dr.DeviceRegistry, device: dr.DeviceEntry) -> None:
    """Link an entity, then remove the device so the link can no longer resolve."""
    await async_link(hass, SOLAR_POWER, device)
    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("entity_entry")
async def test_remove_orphans_lists_the_missing_identifiers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test each choice names the entity and the identifiers nothing answers to."""
    await _async_orphan(hass, device_registry, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_orphans"})

    assert result["step_id"] == "remove_orphans"
    assert _async_offered_links(result) == [{"value": SOLAR_POWER, "label": f"{SOLAR_POWER} (mqtt:8848_5)"}]


@pytest.mark.usefixtures("entity_entry")
async def test_remove_orphans_drops_the_link(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test dropping an unresolved link stops it from being re-applied."""
    await _async_orphan(hass, device_registry, device)

    flow_id = await _async_menu(hass, config_entry)
    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_orphans"})
    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": [SOLAR_POWER]})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.MENU
    assert config_entry.options[LINKS] == {}


@pytest.mark.usefixtures("entity_entry")
async def test_remove_orphans_clears_the_repair_issue(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    issue_registry: ir.IssueRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the repair notice raised for the link goes away with it."""
    await _async_orphan(hass, device_registry, device)
    assert issue_registry.async_get_issue(DOMAIN, f"unresolved_link_{SOLAR_POWER}") is not None

    flow_id = await _async_menu(hass, config_entry)
    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_orphans"})
    await hass.config_entries.options.async_configure(flow_id, {"entity_id": [SOLAR_POWER]})
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, f"unresolved_link_{SOLAR_POWER}") is None


@pytest.mark.usefixtures("entity_entry")
async def test_remove_orphans_keeps_a_link_that_resolves(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test a link whose device is still there is not offered for cleanup."""
    await async_link(hass, SOLAR_POWER, device)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert "remove_orphans" not in _async_menu_options(result)


async def test_remove_orphans_is_not_offered_without_links(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test the menu leaves the cleanup entry out when nothing is recorded at all."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert "remove_orphans" not in _async_menu_options(result)


@pytest.mark.usefixtures("entity_entry")
async def test_remove_orphans_without_selection(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test ticking nothing leaves the step without dropping anything."""
    await _async_orphan(hass, device_registry, device)

    flow_id = await _async_menu(hass, config_entry)
    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_orphans"})
    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": []})

    assert result["type"] is FlowResultType.MENU
    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


@pytest.mark.usefixtures("entity_entry")
async def test_exit_ends_the_flow(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test the menu's exit entry closes the dialog, leaving the links as they are."""
    await async_link(hass, SOLAR_POWER, device)

    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "exit"})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_menu_comes_back_between_changes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test two links can be made in one visit, without reopening the dialog."""
    flow_id = await _async_menu(hass, config_entry)

    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})
    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": device.id}
    )
    assert result["type"] is FlowResultType.MENU

    await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})
    await hass.config_entries.options.async_configure(flow_id, {"entity_id": [GRID_IMPORT], "device_id": device.id})
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert entity_registry.async_get(GRID_IMPORT).device_id == device.id


@pytest.mark.usefixtures("entity_entry")
async def test_menu_offers_remove_link_once_something_is_linked(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test the unlink entry appears as soon as there is a link to unlink."""
    await async_link(hass, SOLAR_POWER, device)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert "remove_link" in _async_menu_options(result)
    assert "remove_orphans" not in _async_menu_options(result)


@pytest.mark.usefixtures("entity_entry")
async def test_menu_offers_remove_orphans_once_one_is_unresolved(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the cleanup entry appears only once a link stops resolving."""
    await _async_orphan(hass, device_registry, device)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert "remove_orphans" in _async_menu_options(result)


@pytest.mark.usefixtures("entity_entry")
async def test_remove_link_returns_to_the_menu_when_emptied_meanwhile(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test the step falls back to the menu rather than a dead-end abort page.

    The menu only offers the step while something is linked, so this is the link
    going away between the menu being drawn and the entry being clicked.
    """
    await async_link(hass, SOLAR_POWER, device)
    flow_id = await _async_menu(hass, config_entry)
    await hass.services.async_call(DOMAIN, "remove_identifier", {"entity_id": SOLAR_POWER}, blocking=True)

    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "remove_link"})

    assert result["type"] is FlowResultType.MENU


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_without_selection(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test submitting the add form empty leaves it without linking anything."""
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": []})

    assert result["type"] is FlowResultType.MENU
    assert LINKS not in config_entry.options or config_entry.options[LINKS] == {}


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_reports_a_half_filled_form(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test picking a device but no entity is reported rather than silently ignored."""
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": [], "device_id": device.id})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "incomplete_link"}


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_reports_an_entity_without_device(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test picking entities but no device is reported rather than silently ignored."""
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(flow_id, {"entity_id": [SOLAR_POWER]})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "incomplete_link"}


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_form_keeps_its_placeholders(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Test neither picker carries a default, which would hide its placeholder.

    A marker with a default reads as already filled in to the frontend, which then
    drops the "Select an entity" placeholder the empty field is meant to show.
    """
    flow_id = await _async_menu(hass, config_entry)
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "add_link"})

    for marker in result["data_schema"].schema:
        assert marker.default is vol.UNDEFINED, f"{marker} carries a default"


@pytest.mark.usefixtures("entity_entry")
async def test_add_link_keeps_what_was_filled_in_on_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test a rejected submission comes back with the fields still filled in.

    The values return as suggested values rather than defaults, so the picker that
    was left empty still shows its own placeholder.
    """
    flow_id = await _async_add_link_form(hass, config_entry)

    result = await hass.config_entries.options.async_configure(
        flow_id, {"entity_id": [SOLAR_POWER], "device_id": "does-not-exist"}
    )

    assert result["errors"] == {"base": "device_id_unknown"}
    suggested = {
        marker.schema: marker.description["suggested_value"]
        for marker in result["data_schema"].schema
        if marker.description
    }
    assert suggested == {"entity_id": [SOLAR_POWER], "device_id": "does-not-exist"}
    assert all(marker.default is vol.UNDEFINED for marker in result["data_schema"].schema)
