"""Test that manual device links survive the owning integration re-adding entities."""

# pyright: reportOptionalMemberAccess=false

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN, LINKS, SOLAR_POWER, async_link

ISSUE_ID = f"unresolved_link_{SOLAR_POWER}"


@pytest.mark.parametrize(
    ("written_device", "expected_device"),
    [
        pytest.param("no_device_id", "device_id", id="cleared_link_is_restored"),
        pytest.param(
            "other_device_id",
            "other_device_id",
            id="device_set_by_owning_integration_is_kept",
        ),
    ],
)
@pytest.mark.usefixtures("config_entry", "entity_entry")
async def test_link_reapplied_after_platform_write(  # pylint: disable=too-many-positional-arguments,too-many-arguments
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    request: pytest.FixtureRequest,
    written_device: str,
    expected_device: str,
) -> None:
    """Test what an owning integration writing a device link leaves behind."""
    await async_link(hass, SOLAR_POWER, device)

    entity_registry.async_update_entity(SOLAR_POWER, device_id=request.getfixturevalue(written_device))
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id == request.getfixturevalue(expected_device)


@pytest.mark.usefixtures("config_entry", "entity_entry")
async def test_reapply_does_not_loop(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, device: dr.DeviceEntry
) -> None:
    """Test re-linking fires one registry update and settles."""
    await async_link(hass, SOLAR_POWER, device)

    events: list[er.EventEntityRegistryUpdatedData] = []
    hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, lambda event: events.append(event.data))

    entity_registry.async_update_entity(SOLAR_POWER, device_id=None)
    await hass.async_block_till_done()

    assert len(events) == 2


@pytest.mark.usefixtures("entity_entry")
async def test_link_persisted(hass: HomeAssistant, config_entry: MockConfigEntry, device: dr.DeviceEntry) -> None:
    """Test the link is recorded in the config entry options."""
    await async_link(hass, SOLAR_POWER, device)

    assert config_entry.options[LINKS] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


@pytest.mark.usefixtures("entity_entry")
async def test_removing_link_stops_reapplying(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test an unlinked entity is not linked again."""
    await async_link(hass, SOLAR_POWER, device)
    await hass.services.async_call(DOMAIN, "remove_identifier", {"entity_id": SOLAR_POWER}, blocking=True)

    assert config_entry.options[LINKS] == {}

    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)
    entity_registry.async_update_entity(SOLAR_POWER, device_id=None)
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id is None


@pytest.mark.usefixtures("entity_entry")
async def test_link_without_loaded_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test linking still works, without persistence, once the entry is unloaded."""
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    await async_link(hass, SOLAR_POWER, device)

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert LINKS not in config_entry.options


@pytest.mark.usefixtures("enable_custom_integrations", "entity_entry")
async def test_link_reapplied_at_startup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test a stored link is applied when the integration sets up."""
    entry = MockConfigEntry(domain=DOMAIN, options={LINKS: {SOLAR_POWER: [["mqtt", "8848_5"]]}})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_stored_link_of_gone_entity_purged(hass: HomeAssistant) -> None:
    """Test a link kept for an entity that no longer exists is dropped."""
    entry = MockConfigEntry(domain=DOMAIN, options={LINKS: {SOLAR_POWER: [["mqtt", "8848_5"]]}})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.options[LINKS] == {}


@pytest.mark.usefixtures("config_entry", "entity_entry")
async def test_link_forgotten_when_entity_removed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test removing the entity drops its stored link."""
    await async_link(hass, SOLAR_POWER, device)

    entity_registry.async_remove(SOLAR_POWER)
    await hass.async_block_till_done()

    assert config_entry.options[LINKS] == {}


@pytest.mark.usefixtures("entity_entry")
async def test_link_follows_renamed_entity(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the stored link follows an entity that is renamed."""
    await async_link(hass, SOLAR_POWER, device)

    entity_registry.async_update_entity(SOLAR_POWER, new_entity_id="sensor.renamed")
    await hass.async_block_till_done()

    assert config_entry.options[LINKS] == {"sensor.renamed": [["mqtt", "8848_5"]]}
    assert entity_registry.async_get("sensor.renamed").device_id == device.id


@pytest.mark.usefixtures("config_entry", "entity_entry")
async def test_missing_device_raises_issue(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test a link that can no longer be resolved raises a repair issue."""
    await async_link(hass, SOLAR_POWER, device)

    device_registry.async_remove_device(device.id)
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id is None
    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID) is not None


@pytest.mark.usefixtures("config_entry", "entity_entry")
async def test_issue_cleared_when_link_applies(
    hass: HomeAssistant,
    issue_registry: ir.IssueRegistry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test the repair issue disappears once the link can be applied again."""
    await async_link(hass, SOLAR_POWER, device)

    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID) is None

    entity_registry.async_update_entity(SOLAR_POWER, device_id=None)
    await hass.async_block_till_done()

    assert issue_registry.async_get_issue(DOMAIN, ISSUE_ID) is None
