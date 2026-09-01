"""Constants for the Device Link Tools integration."""

import logging

DOMAIN = "device_link_tools"

LOGGER = logging.getLogger(__package__)

# Devices are resolved through async_get(include_child_devices=..., include_composite_devices=...)
# and dr.ChildDeviceEntry, none of which exist before 2026.9. On an older core the
# integration would import or fail mid-action, so refuse to set up instead.
MINIMUM_HA_VERSION = (2026, 9)

SERVICE_ADD_IDENTIFIER = "add_identifier"
SERVICE_READ_IDENTIFIERS = "read_identifiers"
SERVICE_REMOVE_IDENTIFIER = "remove_identifier"

ATTR_CONNECTIONS = "connections"
ATTR_IDENTIFIER = "identifier"
ATTR_IDENTIFIERS = "identifiers"
ATTR_SOURCE_ENTITY_ID = "source_entity_id"
ATTR_UNCHANGED = "unchanged"
ATTR_UPDATED = "updated"

CONF_LINKS = "links"
