"""Actions to link entities to a device by hand."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportReturnType=false

from typing import Any

import voluptuous as vol

from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, ATTR_NAME
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    ATTR_CONNECTIONS,
    ATTR_IDENTIFIERS,
    ATTR_SOURCE_ENTITY_ID,
    ATTR_UNCHANGED,
    ATTR_UPDATED,
    DOMAIN,
    SERVICE_ADD_IDENTIFIER,
    SERVICE_READ_IDENTIFIERS,
    SERVICE_REMOVE_IDENTIFIER,
)
from .helpers import (
    as_pairs,
    async_device_identifiers,
    async_resolve_device,
    async_resolve_device_id,
    async_resolve_entry,
    parse_identifiers,
)
from .reapply import async_apply_link

ENTITY_IDS: Any = vol.All(cv.ensure_list, cv.entity_ids_or_uuids)

READ_IDENTIFIERS_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id_or_uuid})

ADD_IDENTIFIER_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): ENTITY_IDS,
        vol.Exclusive(ATTR_IDENTIFIERS, "device"): parse_identifiers,
        vol.Exclusive(ATTR_DEVICE_ID, "device"): cv.string,
        vol.Exclusive(ATTR_SOURCE_ENTITY_ID, "device"): cv.entity_id_or_uuid,
    }
)

REMOVE_IDENTIFIER_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): ENTITY_IDS})


async def async_read_identifiers(call: ServiceCall) -> ServiceResponse:
    """Read the identifiers of the device an entity is linked to.

    Args:
        call (ServiceCall): The service call.

    Returns:
        ServiceResponse: The device identifiers.

    """
    entity_registry = er.async_get(call.hass)
    entry = async_resolve_entry(entity_registry, call.data[ATTR_ENTITY_ID])

    if entry.device_id is None:
        return {
            ATTR_ENTITY_ID: entry.entity_id,
            ATTR_DEVICE_ID: None,
            ATTR_IDENTIFIERS: [],
            ATTR_CONNECTIONS: [],
            ATTR_NAME: None,
        }

    identifiers, connections, name = async_device_identifiers(call.hass, entry.device_id)
    return {
        ATTR_ENTITY_ID: entry.entity_id,
        ATTR_DEVICE_ID: entry.device_id,
        ATTR_IDENTIFIERS: as_pairs(identifiers),
        ATTR_CONNECTIONS: as_pairs(connections),
        ATTR_NAME: name,
    }


async def async_add_identifier(call: ServiceCall) -> ServiceResponse:
    """Link entities to a device, designated in one of three ways.

    Args:
        call (ServiceCall): The service call.

    Returns:
        ServiceResponse: The result of the operation.

    """
    device = _async_target_device(call)
    updated, unchanged = async_apply_link(call.hass, call.data[ATTR_ENTITY_ID], device)
    return _async_response(device, updated, unchanged)


async def async_remove_identifier(call: ServiceCall) -> ServiceResponse:
    """Unlink entities from the device they are linked to.

    Args:
        call (ServiceCall): The service call.

    Returns:
        ServiceResponse: The result of the operation.

    """
    updated, unchanged = async_apply_link(call.hass, call.data[ATTR_ENTITY_ID], None)
    return _async_response(None, updated, unchanged)


@callback
def _async_target_device(call: ServiceCall) -> dr.DeviceEntry:
    """Return the device the call designates, whichever field carries it.

    Args:
        call (ServiceCall): The service call.

    Returns:
        dr.DeviceEntry: The device entry.

    Raises:
        ServiceValidationError: If no device target is specified.

    """
    if (device_id := call.data.get(ATTR_DEVICE_ID)) is not None:
        return async_resolve_device_id(call.hass, device_id)
    if (identifiers := call.data.get(ATTR_IDENTIFIERS)) is not None:
        return async_resolve_device(call.hass, identifiers)
    if (source_entity_id := call.data.get(ATTR_SOURCE_ENTITY_ID)) is not None:
        return _async_device_of(call.hass, source_entity_id)
    raise ServiceValidationError(translation_domain=DOMAIN, translation_key="device_target_required")


@callback
def _async_device_of(hass: HomeAssistant, entity_id: str) -> dr.DeviceEntry:
    """Return the device another entity is linked to.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_id (str): The entity ID.

    Returns:
        dr.DeviceEntry: The device entry.

    Raises:
        ServiceValidationError: If the entity is not linked to a device.

    """
    entry = async_resolve_entry(er.async_get(hass), entity_id)
    if entry.device_id is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="source_not_linked",
            translation_placeholders={"entity_id": entry.entity_id},
        )
    # Through the same resolution as a picked device, so a composite or an
    # identifier-less device is refused here too rather than at write time.
    return async_resolve_device_id(hass, entry.device_id)


@callback
def _async_response(device: dr.DeviceEntry | None, updated: list[str], unchanged: list[str]) -> ServiceResponse:
    """Report what the call did.

    Args:
        device (dr.DeviceEntry | None): The device entry or None.
        updated (list[str]): The updated entity IDs.
        unchanged (list[str]): The unchanged entity IDs.

    Returns:
        ServiceResponse: The response data.

    """
    return {
        ATTR_DEVICE_ID: device.id if device else None,
        ATTR_IDENTIFIERS: as_pairs(device.identifiers) if device else [],
        ATTR_UPDATED: updated,
        ATTR_UNCHANGED: unchanged,
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the device link tools actions.

    Args:
        hass (HomeAssistant): The Home Assistant instance.

    """
    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_IDENTIFIERS,
        async_read_identifiers,
        schema=READ_IDENTIFIERS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    for service_name, handler, schema in (
        (SERVICE_ADD_IDENTIFIER, async_add_identifier, ADD_IDENTIFIER_SCHEMA),
        (SERVICE_REMOVE_IDENTIFIER, async_remove_identifier, REMOVE_IDENTIFIER_SCHEMA),
    ):
        async_register_admin_service(
            hass,
            DOMAIN,
            service_name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
