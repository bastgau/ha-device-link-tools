"""Fixtures for the Device Link Tools integration."""

# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument

from collections.abc import Generator
import importlib
import pathlib
import sys
from typing import Any

import attr
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from tests.testing_config.common import MockConfigEntry

DOMAIN = "device_link_tools"
SOURCE = pathlib.Path(__file__).parents[1] / "custom_components" / DOMAIN
COMPOSITE_DEVICE_ID = "composite0000000000000000000000"
SOLAR_POWER = "sensor.solar_power"
GRID_IMPORT = "sensor.grid_import"
LINKS = "links"


async def async_link(hass: HomeAssistant, entity_id: str, device: dr.DeviceEntry) -> None:
    """Link an entity to a device the way a user would, through the action."""
    await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": entity_id, "device_id": device.id},
        blocking=True,
    )


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Provide a config directory holding the integration under test.

    Symlinked rather than copied so that coverage, which tracks the source file by
    path, sees the code the tests actually run.
    """
    target = pathlib.Path(hass_tmp_config_dir) / "custom_components" / DOMAIN
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(SOURCE)
    return hass_tmp_config_dir


@pytest.fixture(autouse=True)
def reset_custom_components_import() -> Generator[None]:
    """Import custom_components from this test's config directory.

    Another test may have bound the name to a different directory earlier in the
    session, and the loader would then never see the copy made above.
    """
    _drop_custom_components()
    yield
    _drop_custom_components()


def _drop_custom_components() -> None:
    """Remove custom_components from sys.modules and invalidate caches."""
    for name in [name for name in sys.modules if name == "custom_components" or name.startswith("custom_components.")]:
        del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
async def config_entry(
    hass: HomeAssistant,
    enable_custom_integrations: None,
) -> MockConfigEntry:
    """Set up the integration and return its config entry."""
    entry = MockConfigEntry(domain=DOMAIN, title="Device Link Tools")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def owning_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return the config entry owning the devices used in the tests."""
    entry = MockConfigEntry(domain="mqtt", title="MQTT")
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def device(device_registry: dr.DeviceRegistry, owning_entry: MockConfigEntry) -> dr.DeviceEntry:
    """Return a device an entity can be linked to."""
    return device_registry.async_get_or_create(
        config_entry_id=owning_entry.entry_id,
        identifiers={("mqtt", "8848_5")},
        connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff")},
        name="Boiler",
    )


@pytest.fixture
def other_device(device_registry: dr.DeviceRegistry, owning_entry: MockConfigEntry) -> dr.DeviceEntry:
    """Return a second, unrelated device."""
    return device_registry.async_get_or_create(
        config_entry_id=owning_entry.entry_id,
        identifiers={("mqtt", "9000_1")},
        name="Heat pump",
    )


@pytest.fixture
def colliding_device(hass: HomeAssistant, device_registry: dr.DeviceRegistry, device: dr.DeviceEntry) -> dr.DeviceEntry:
    """Return a device of another config entry carrying the same identifiers."""
    other_owner = MockConfigEntry(domain="tasmota", title="Tasmota")
    other_owner.add_to_hass(hass)
    return device_registry.async_get_or_create(
        config_entry_id=other_owner.entry_id,
        identifiers={("mqtt", "8848_5")},
        name="Boiler bis",
    )


@pytest.fixture
def no_device_id() -> None:
    """Return the absence of a device link."""
    return


@pytest.fixture
def device_id(device: dr.DeviceEntry) -> str:
    """Return the id of the boiler device."""
    return device.id


@pytest.fixture
def other_device_id(other_device: dr.DeviceEntry) -> str:
    """Return the id of the heat pump device."""
    return other_device.id


@pytest.fixture
async def composite_linked_entity(hass: HomeAssistant, hass_storage: dict[str, Any]) -> str:
    """Register an entity holding the id of a pre-migration composite device.

    A composite only exists once the device registry has migrated a device that
    belonged to two config entries, so this needs load_registries=False and loads the
    registries itself. Returns the composite device id.
    """
    owner = MockConfigEntry(domain="mqtt", title="MQTT")
    owner.add_to_hass(hass)
    second_owner = MockConfigEntry(domain="tasmota", title="Tasmota")
    second_owner.add_to_hass(hass)

    hass_storage[dr.STORAGE_KEY] = {
        "version": 1,
        "minor_version": 12,
        "key": dr.STORAGE_KEY,
        "data": {
            "devices": [
                {
                    "area_id": None,
                    "config_entries": [owner.entry_id, second_owner.entry_id],
                    "config_entries_subentries": {
                        owner.entry_id: [None],
                        second_owner.entry_id: [None],
                    },
                    "configuration_url": None,
                    "connections": [["mac", "aa:bb:cc:dd:ee:ff"]],
                    "created_at": "1970-01-01T00:00:00+00:00",
                    "disabled_by": None,
                    "entry_type": None,
                    "hw_version": None,
                    "id": COMPOSITE_DEVICE_ID,
                    "identifiers": [["mqtt", "8848_5"], ["tasmota", "8848"]],
                    "labels": [],
                    "manufacturer": None,
                    "model": None,
                    "model_id": None,
                    "modified_at": "1970-01-01T00:00:00+00:00",
                    "name": "Boiler",
                    "name_by_user": None,
                    "primary_config_entry": owner.entry_id,
                    "serial_number": None,
                    "sw_version": None,
                    "via_device_id": None,
                }
            ],
            "deleted_devices": [],
        },
    }

    dr.async_setup(hass)
    await dr.async_load(hass)
    await er.async_load(hass)

    device_registry = dr.async_get(hass)
    assert device_registry.async_get(COMPOSITE_DEVICE_ID, include_composite_devices=False) is None
    assert len(device_registry.async_get_devices_for_composite_device_id(COMPOSITE_DEVICE_ID)) == 2

    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_or_create(
        "sensor", "rest", "solar-power", suggested_object_id="solar_power"
    ).entity_id

    # An entity migrated alongside the device still holds the composite id, a state
    # async_update_entity refuses to produce. Write the entry the way the registry
    # writes it internally, which is also what loading it from storage would give.
    entity_registry.entities[entity_id] = attr.evolve(
        entity_registry.entities[entity_id], device_id=COMPOSITE_DEVICE_ID
    )

    return COMPOSITE_DEVICE_ID


@pytest.fixture
def entity_entry(entity_registry: er.EntityRegistry) -> er.RegistryEntry:
    """Return a registered entity that is not linked to any device."""
    return entity_registry.async_get_or_create(
        "sensor",
        "rest",
        "solar-power",
        suggested_object_id="solar_power",
    )


@pytest.fixture
def second_entity_entry(entity_registry: er.EntityRegistry) -> er.RegistryEntry:
    """Return a second registered entity that is not linked to any device."""
    return entity_registry.async_get_or_create(
        "sensor",
        "rest",
        "grid-import",
        suggested_object_id="grid_import",
    )
