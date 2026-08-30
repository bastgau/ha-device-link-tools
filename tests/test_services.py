"""Test the Device Link Tools actions."""

# pyright: reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false
# pyright: reportUnknownLambdaType=false

from typing import Any

import pytest
import voluptuous as vol

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.typing import UNDEFINED
from tests.testing_config.common import MockConfigEntry, MockUser

from .conftest import DOMAIN, GRID_IMPORT, SOLAR_POWER, async_link

pytestmark = pytest.mark.usefixtures("config_entry")


@pytest.mark.parametrize(
    ("linked_device", "identifiers", "connections", "name"),
    [
        pytest.param("no_device_id", [], [], None, id="unlinked"),
        pytest.param(
            "device_id",
            [["mqtt", "8848_5"]],
            [["mac", "aa:bb:cc:dd:ee:ff"]],
            "Boiler",
            id="linked",
        ),
    ],
)
@pytest.mark.usefixtures("entity_entry", "device")
async def test_read_identifiers(  # pylint: disable=too-many-positional-arguments,too-many-arguments
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    request: pytest.FixtureRequest,
    linked_device: str,
    identifiers: list[list[str]],
    connections: list[list[str]],
    name: str | None,
) -> None:
    """Test reading the device link of an entity."""
    device_id = request.getfixturevalue(linked_device)
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device_id)

    response = await hass.services.async_call(
        DOMAIN,
        "read_identifiers",
        {"entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
    )

    assert response == {
        "entity_id": SOLAR_POWER,
        "device_id": device_id,
        "identifiers": identifiers,
        "connections": connections,
        "name": name,
    }


@pytest.mark.parametrize(
    "identifiers",
    [
        pytest.param("mqtt:8848_5", id="colon_string"),
        pytest.param(["mqtt:8848_5"], id="colon_string_list"),
        pytest.param([["mqtt", "8848_5"]], id="pair_list"),
        pytest.param({"domain": "mqtt", "identifier": "8848_5"}, id="mapping"),
        pytest.param([{"domain": "mqtt", "identifier": "8848_5"}], id="mapping_list"),
    ],
)
@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_accepted_formats(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    identifiers: Any,
) -> None:
    """Test every accepted spelling of the identifiers field."""
    await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": SOLAR_POWER, "identifiers": identifiers},
        blocking=True,
    )

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id


@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_by_device_id(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test picking the device by id records the same link as its identifiers."""
    response = await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": SOLAR_POWER, "device_id": device.id},
        blocking=True,
        return_response=True,
    )

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert response["identifiers"] == [["mqtt", "8848_5"]]
    assert config_entry.options["links"] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("device_id", id="picked_by_id"),
        pytest.param("source_entity_id", id="taken_from_a_source_entity"),
    ],
)
@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_device_without_identifiers(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    owning_entry: MockConfigEntry,
    field: str,
) -> None:
    """Test a device known only by its connections cannot hold a durable link."""
    device = device_registry.async_get_or_create(
        config_entry_id=owning_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "11:22:33:44:55:66")},
        name="Connections only",
    )
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)
    designations = {"device_id": device.id, "source_entity_id": SOLAR_POWER}

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": GRID_IMPORT, field: designations[field]},
            blocking=True,
        )

    assert err.value.translation_key == "device_without_identifiers"


@pytest.mark.parametrize(
    "field",
    [
        pytest.param("device_id", id="picked_by_id"),
        pytest.param("source_entity_id", id="taken_from_a_source_entity"),
    ],
)
@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_child_device(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    owning_entry: MockConfigEntry,
    device: dr.DeviceEntry,
    field: str,
) -> None:
    """Test a child device cannot hold a link, since only its parent is searchable."""
    child = device_registry.async_get_or_create_child(
        config_entry_id=owning_entry.entry_id,
        identifiers={("mqtt", "8848_5_burner")},
        parent_device_id=device.id,
        name="Burner",
    )
    entity_registry.async_update_entity(SOLAR_POWER, device_id=child.id)
    designations = {"device_id": child.id, "source_entity_id": SOLAR_POWER}

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": GRID_IMPORT, field: designations[field]},
            blocking=True,
        )

    assert err.value.translation_key == "device_is_child"
    assert entity_registry.async_get(GRID_IMPORT).device_id is None


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_multiple_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test linking several entities at once and the reported outcome."""
    response = await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": [SOLAR_POWER, GRID_IMPORT], "identifiers": "mqtt:8848_5"},
        blocking=True,
        return_response=True,
    )

    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert entity_registry.async_get(GRID_IMPORT).device_id == device.id
    assert response == {
        "device_id": device.id,
        "identifiers": [["mqtt", "8848_5"]],
        "updated": [SOLAR_POWER, GRID_IMPORT],
        "unchanged": [],
    }


@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_reports_unchanged(hass: HomeAssistant, device: dr.DeviceEntry) -> None:  # pylint: disable=unused-argument
    """Test an entity already linked to the device is reported as unchanged."""
    data = {"entity_id": SOLAR_POWER, "identifiers": "mqtt:8848_5"}
    await hass.services.async_call(DOMAIN, "add_identifier", data, blocking=True)

    response = await hass.services.async_call(DOMAIN, "add_identifier", data, blocking=True, return_response=True)

    assert response["updated"] == []
    assert response["unchanged"] == [SOLAR_POWER]


@pytest.mark.parametrize(
    ("service", "data", "extra_fixtures", "translation_key"),
    [
        pytest.param(
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": "mqtt:nope"},
            (),
            "device_not_found",
            id="no_device_carries_the_identifiers",
        ),
        pytest.param(
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": "mqtt:8848_5"},
            ("colliding_device",),
            "identifiers_ambiguous",
            id="two_devices_carry_the_identifiers",
        ),
        pytest.param(
            "add_identifier",
            {"entity_id": "sensor.not_registered", "identifiers": "mqtt:8848_5"},
            (),
            "entity_not_registered",
            id="entity_has_no_registry_entry",
        ),
        pytest.param(
            "remove_identifier",
            {"entity_id": "sensor.not_registered"},
            (),
            "entity_not_registered",
            id="unlinking_an_entity_without_registry_entry",
        ),
        pytest.param(
            "add_identifier",
            {"entity_id": GRID_IMPORT, "source_entity_id": SOLAR_POWER},
            (),
            "source_not_linked",
            id="source_entity_has_no_device",
        ),
        pytest.param(
            "add_identifier",
            {"entity_id": SOLAR_POWER, "device_id": "does-not-exist"},
            (),
            "device_id_unknown",
            id="device_id_does_not_exist",
        ),
        pytest.param(
            "add_identifier",
            {"entity_id": SOLAR_POWER},
            (),
            "device_target_required",
            id="neither_device_nor_identifiers",
        ),
    ],
)
@pytest.mark.usefixtures("entity_entry", "second_entity_entry", "device")
async def test_service_validation_error(  # pylint: disable=too-many-positional-arguments,too-many-arguments
    hass: HomeAssistant,
    request: pytest.FixtureRequest,
    service: str,
    data: dict[str, Any],
    extra_fixtures: tuple[str, ...],
    translation_key: str,
) -> None:
    """Test the input errors reported to the user."""
    for fixture in extra_fixtures:
        request.getfixturevalue(fixture)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)

    assert err.value.translation_key == translation_key


@pytest.mark.parametrize(
    "identifiers",
    [
        pytest.param([], id="empty"),
        pytest.param("mqtt", id="missing_separator"),
        pytest.param(":8848_5", id="missing_domain"),
        pytest.param([["mqtt", "8848_5", "extra"]], id="too_many_items"),
        pytest.param([{"domain": "mqtt"}], id="incomplete_mapping"),
        pytest.param([{"a": "1", "b": "2"}], id="mapping_without_domain_key"),
        pytest.param(["mqtt", "8848_5"], id="bare_pair"),
        pytest.param({"mqtt": "8848_5"}, id="single_key_mapping"),
        pytest.param([12], id="not_an_identifier"),
        pytest.param(12, id="not_a_list_of_identifiers"),
    ],
)
@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_invalid_input(hass: HomeAssistant, identifiers: Any) -> None:
    """Test malformed identifiers are rejected by the schema."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": identifiers},
            blocking=True,
        )


@pytest.mark.usefixtures("entity_entry", "device")
async def test_add_identifier_update_rejected(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test a registry rejection is reported as a validation error."""

    def _reject(self: er.EntityRegistry, entity_id: str, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        msg = f"Device {kwargs['device_id']} does not exist"
        raise ValueError(msg)

    monkeypatch.setattr(er.EntityRegistry, "async_update_entity", _reject)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": "mqtt:8848_5"},
            blocking=True,
        )

    assert err.value.translation_key == "update_failed"


@pytest.mark.usefixtures("entity_entry")
async def test_add_identifier_refused_link(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    device: dr.DeviceEntry,  # pylint: disable=unused-argument
) -> None:
    """Test a link the entity registry silently drops is reported as an error."""
    monkeypatch.setattr(
        er.EntityRegistry,
        "_ignore_composite_device_id",
        lambda self, platform, device_id: UNDEFINED,  # pyright: ignore[reportUnknownArgumentType]
    )

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": "mqtt:8848_5"},
            blocking=True,
        )

    assert err.value.translation_key == "link_refused"


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_records_a_partial_write(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    monkeypatch: pytest.MonkeyPatch,
    device: dr.DeviceEntry,
) -> None:
    """Test the entities written before a failure are still recorded."""
    original = er.EntityRegistry.async_update_entity

    def _fail_on_second(self: er.EntityRegistry, entity_id: str, **kwargs: Any) -> Any:
        if entity_id == GRID_IMPORT:
            msg = "boom"
            raise ValueError(msg)
        return original(self, entity_id, **kwargs)

    monkeypatch.setattr(er.EntityRegistry, "async_update_entity", _fail_on_second)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": [SOLAR_POWER, GRID_IMPORT], "device_id": device.id},
            blocking=True,
        )

    # The first entity was written to the registry, so it has to be recorded too:
    # a link this integration does not remember is one it can no longer undo.
    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert config_entry.options["links"] == {SOLAR_POWER: [["mqtt", "8848_5"]]}


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_records_nothing_when_the_first_write_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
    device: dr.DeviceEntry,
) -> None:
    """Test nothing is recorded when no entity was written at all."""

    def _reject(self: er.EntityRegistry, entity_id: str, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        msg = "boom"
        raise ValueError(msg)

    monkeypatch.setattr(er.EntityRegistry, "async_update_entity", _reject)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": [SOLAR_POWER, GRID_IMPORT], "device_id": device.id},
            blocking=True,
        )

    assert "links" not in config_entry.options


async def test_add_identifier_without_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Test an empty entity list is a no-op that records nothing."""
    response = await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": [], "device_id": device.id},
        blocking=True,
        return_response=True,
    )

    assert response["updated"] == []
    assert response["unchanged"] == []
    assert "links" not in config_entry.options


@pytest.mark.usefixtures("entity_entry")
async def test_remove_identifier(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test unlinking an entity from the device this integration put it on."""
    await async_link(hass, SOLAR_POWER, device)

    response = await hass.services.async_call(
        DOMAIN,
        "remove_identifier",
        {"entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
    )

    assert entity_registry.async_get(SOLAR_POWER).device_id is None
    assert response == {
        "device_id": None,
        "identifiers": [],
        "updated": [SOLAR_POWER],
        "unchanged": [],
    }


@pytest.mark.usefixtures("entity_entry", "second_entity_entry")
async def test_add_identifier_from_source_entity(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test taking the device from another entity already linked to it."""
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    response = await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": GRID_IMPORT, "source_entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
    )

    assert entity_registry.async_get(GRID_IMPORT).device_id == device.id
    assert response["device_id"] == device.id
    assert response["identifiers"] == [["mqtt", "8848_5"]]


@pytest.mark.parametrize(
    ("service", "data"),
    [
        pytest.param(
            "add_identifier",
            {"entity_id": SOLAR_POWER, "identifiers": "mqtt:8848_5"},
            id="add_identifier",
        ),
        pytest.param("remove_identifier", {"entity_id": SOLAR_POWER}, id="remove_identifier"),
        pytest.param(
            "add_identifier",
            {"entity_id": GRID_IMPORT, "source_entity_id": SOLAR_POWER},
            id="add_identifier_from_source",
        ),
    ],
)
@pytest.mark.usefixtures("entity_entry", "second_entity_entry", "device")
async def test_mutations_require_admin(
    hass: HomeAssistant,
    hass_read_only_user: MockUser,
    service: str,
    data: dict[str, Any],
) -> None:
    """Test a non-admin user cannot rewrite the registry."""
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            data,
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )


@pytest.mark.usefixtures("entity_entry")
async def test_read_allowed_for_non_admin(hass: HomeAssistant, hass_read_only_user: MockUser) -> None:
    """Test reading is not restricted to administrators."""
    response = await hass.services.async_call(
        DOMAIN,
        "read_identifiers",
        {"entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
        context=Context(user_id=hass_read_only_user.id),
    )

    assert response["device_id"] is None


@pytest.mark.parametrize(
    "target_device",
    [
        pytest.param("other_device", id="moved_to_another_device"),
        pytest.param("device", id="same_device_reasserted"),
    ],
)
@pytest.mark.usefixtures("entity_entry", "other_device")
async def test_add_identifier_refuses_a_link_set_elsewhere(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    request: pytest.FixtureRequest,
    device: dr.DeviceEntry,
    target_device: str,
) -> None:
    """Test an entity linked by something else is not moved, even to its own device.

    Re-asserting the same device must not be treated as a no-op either: letting it
    through would start tracking a link this integration did not create, which the
    next unlink/relink call could then move.
    """
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_identifier",
            {"entity_id": SOLAR_POWER, "device_id": request.getfixturevalue(target_device).id},
            blocking=True,
        )

    assert err.value.translation_key == "link_set_elsewhere"
    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id
    assert SOLAR_POWER not in config_entry.options.get("links", {})


@pytest.mark.usefixtures("entity_entry")
async def test_moving_a_link_we_recorded(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
    other_device: dr.DeviceEntry,
) -> None:
    """Test a link recorded here is re-pointed in a single call."""
    await async_link(hass, SOLAR_POWER, device)

    await hass.services.async_call(
        DOMAIN,
        "add_identifier",
        {"entity_id": SOLAR_POWER, "device_id": other_device.id},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert entity_registry.async_get(SOLAR_POWER).device_id == other_device.id
    assert config_entry.options["links"] == {SOLAR_POWER: [["mqtt", "9000_1"]]}


@pytest.mark.usefixtures("entity_entry")
async def test_remove_identifier_refuses_a_link_set_elsewhere(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device: dr.DeviceEntry,
) -> None:
    """Test a link this integration did not record is not removed either."""
    entity_registry.async_update_entity(SOLAR_POWER, device_id=device.id)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "remove_identifier", {"entity_id": SOLAR_POWER}, blocking=True)

    assert err.value.translation_key == "link_set_elsewhere"
    assert entity_registry.async_get(SOLAR_POWER).device_id == device.id


@pytest.mark.usefixtures("entity_entry")
async def test_remove_identifier_of_an_unlinked_entity(hass: HomeAssistant) -> None:
    """Test unlinking an entity that has no device is a no-op, not an error."""
    response = await hass.services.async_call(
        DOMAIN,
        "remove_identifier",
        {"entity_id": SOLAR_POWER},
        blocking=True,
        return_response=True,
    )

    assert response["updated"] == []
    assert response["unchanged"] == [SOLAR_POWER]
