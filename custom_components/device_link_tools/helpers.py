"""Helpers to read and rewrite the device link of an entity registry entry."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportReturnType=false

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
)

from .const import ATTR_IDENTIFIER, DOMAIN

type Identifiers = set[tuple[str, str]]


def parse_identifier(value: Any) -> tuple[str, str]:
    """Coerce a single device identifier into a (domain, identifier) tuple.

    Args:
        value (Any): The identifier value to parse.

    Returns:
        tuple[str, str]: A tuple of (domain, identifier).

    """
    if isinstance(value, str):
        domain, separator, identifier = value.partition(":")
        if not separator or not domain or not identifier:
            raise_msg = f"expected an identifier of the form 'domain:identifier', got {value!r}"
            raise vol.Invalid(raise_msg)
        return (domain, identifier)

    if isinstance(value, Mapping):
        domain: Any = value.get(CONF_DOMAIN)
        identifier = value.get(ATTR_IDENTIFIER)
        if domain is None or identifier is None:
            keys = sorted(str(key) for key in value)
            msg = f"expected a mapping with the keys 'domain' and 'identifier', got {keys}"
            raise vol.Invalid(msg)
        return (str(domain), str(identifier))

    if isinstance(value, (list, tuple)):
        value_len = len(value)
        if value_len != 2:
            msg = f"expected an identifier of exactly 2 items, got {value_len}"
            raise vol.Invalid(msg)
        return (str(value[0]), str(value[1]))

    raise_msg = f"invalid device identifier: {value!r}"
    raise vol.Invalid(raise_msg)


def parse_identifiers(value: Any) -> Identifiers:
    """Validate the identifiers field into a set of (domain, identifier) tuples.

    A string or a mapping may be given on its own or in a list. A pair has to be inside
    a list, a bare two-item list being read as two identifiers.

    Args:
        value (Any): The identifiers value to parse.

    Returns:
        Identifiers: A set of (domain, identifier) tuples.

    """
    items: list[Any] = value if isinstance(value, list) else [value]
    if not (identifiers := {parse_identifier(item) for item in items}):
        raise_msg = "expected at least one device identifier"
        raise vol.Invalid(raise_msg)
    return identifiers


def format_identifiers(identifiers: Identifiers) -> str:
    """Format identifiers for an error message.

    Args:
        identifiers (Identifiers): The identifiers to format.

    Returns:
        str: Formatted identifiers string.

    """
    return ", ".join(sorted(f"{domain}:{value}" for domain, value in identifiers))


def as_pairs(values: set[tuple[str, str]]) -> list[list[str]]:
    """Convert registry tuples to the plain lists a service response allows.

    Args:
        values (set[tuple[str, str]]): The registry tuples to convert.

    Returns:
        list[list[str]]: Plain lists representation.

    """
    return sorted([first, second] for first, second in values)


@callback
def async_resolve_entry(entity_registry: er.EntityRegistry, entity_id_or_uuid: str) -> er.RegistryEntry:
    """Return the registry entry of an entity, or explain why there is none.

    Args:
        entity_registry (er.EntityRegistry): The entity registry.
        entity_id_or_uuid (str): The entity ID or UUID.

    Returns:
        er.RegistryEntry: The registry entry.

    Raises:
        ServiceValidationError: If the entity is not registered.

    """
    if (entry := entity_registry.async_get(entity_id_or_uuid)) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entity_not_registered",
            translation_placeholders={"entity_id": entity_id_or_uuid},
        )
    return entry


def device_label(device: dr.AnyDeviceEntry | None, device_id: str) -> str:
    """Return the name to show for a device, falling back to its id.

    Args:
        device (dr.AnyDeviceEntry | None): The device entry or None.
        device_id (str): The device ID.

    Returns:
        str: The device label.

    """
    if device is None:
        return device_id
    return device.name_by_user or device.name or device_id


@callback
def async_resolve_device(hass: HomeAssistant, identifiers: Identifiers) -> dr.DeviceEntry:
    """Resolve identifiers to the single device they designate.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        identifiers (Identifiers): The device identifiers.

    Returns:
        dr.DeviceEntry: The device entry.

    Raises:
        ServiceValidationError: If no device is found or multiple devices match.

    """
    device_registry = dr.async_get(hass)

    # Deliberately not async_get_device: it collapses the splits of a pre-migration
    # composite device into a composite whose id async_update_entity then silently
    # refuses. async_get_devices only ever returns registered devices.
    matches = device_registry.async_get_devices(identifiers=identifiers)

    if not matches:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_not_found",
            translation_placeholders={"identifiers": format_identifiers(identifiers)},
        )

    if len(matches) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="identifiers_ambiguous",
            translation_placeholders={
                "identifiers": format_identifiers(identifiers),
                "devices": ", ".join(sorted(f"{device_label(device, device.id)} ({device.id})" for device in matches)),
            },
        )

    return matches[0]


@callback
def async_resolve_device_id(hass: HomeAssistant, device_id: str) -> dr.DeviceEntry:
    """Resolve a device id to a device an entity can be linked to.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        device_id (str): The device ID.

    Returns:
        dr.DeviceEntry: The device entry.

    Raises:
        ServiceValidationError: If the device is composite, a child, unknown, or has no identifiers.

    """
    device_registry = dr.async_get(hass)

    # Only a plain registered device can hold a durable link, so resolve with the other
    # two kinds excluded and tell them apart afterwards:
    #  - a composite is synthesized on demand for a pre-migration id, and the entity
    #    registry silently declines an update pointing at one;
    #  - a child device is accepted by the entity registry, but async_get_devices
    #    searches main devices only, so async_resolve_device could never find it again
    #    and the link would be dropped at the next restart.
    device = device_registry.async_get(device_id, include_child_devices=False, include_composite_devices=False)
    if device is None:
        # async_get with every kind allowed: None here means the id is simply unknown.
        other = device_registry.async_get(device_id)
        if other is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_id_unknown",
                translation_placeholders={"device_id": device_id},
            )
        if isinstance(other, dr.ChildDeviceEntry):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_is_child",
                translation_placeholders={"name": device_label(other, device_id)},
            )
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_id_composite",
            translation_placeholders={"device_id": device_id},
        )

    if not device.identifiers:
        # The link is recorded by identifiers so it can be re-applied; a device that has
        # none could only be linked until the next restart.
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="device_without_identifiers",
            translation_placeholders={
                "device_id": device_id,
                "name": device_label(device, device_id),
            },
        )

    return device


@callback
def async_device_identifiers(hass: HomeAssistant, device_id: str) -> tuple[Identifiers, Identifiers, str | None]:
    """Return the identifiers, connections and name behind a linked device id.

    An entity can hold the id of a pre-migration composite device. async_get synthesizes
    a read-only composite from the devices it was split into, so the identifiers and
    connections returned for such an id are the union of theirs.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        device_id (str): The device ID.

    Returns:
        tuple[Identifiers, Identifiers, str | None]: A tuple of (identifiers, connections, name).

    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return set(), set(), None
    identifiers: Identifiers = device.identifiers or set()
    # A child device has no connections at all: reading the attribute goes through a
    # compatibility shim that returns an empty set and is removed in 2027.9.
    connections: Identifiers = set() if isinstance(device, dr.ChildDeviceEntry) else device.connections or set()
    result: Any = (identifiers, connections, device.name_by_user or device.name)
    return result


@callback
def async_set_device_link(entity_registry: er.EntityRegistry, entity_id: str, device_id: str | None) -> bool:
    """Set or clear the device link of a registry entry, returning whether it changed.

    Args:
        entity_registry (er.EntityRegistry): The entity registry.
        entity_id (str): The entity ID.
        device_id (str | None): The device ID or None to clear the link.

    Returns:
        bool: True if the link was changed.

    Raises:
        ServiceValidationError: If the entity is not registered or the update fails.
        HomeAssistantError: If the device link is refused.

    """
    entry = async_resolve_entry(entity_registry, entity_id)
    if entry.device_id == device_id:
        return False

    try:
        updated = entity_registry.async_update_entity(entry.entity_id, device_id=device_id)
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={
                "entity_id": entry.entity_id,
                "error": str(err),
            },
        ) from err

    if updated.device_id != device_id:
        # The entity registry declines composite device ids by dropping the update
        # instead of raising, which would otherwise be reported as a success.
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="link_refused",
            translation_placeholders={
                "entity_id": entry.entity_id,
                "device_id": device_id or "",
            },
        )

    return True
