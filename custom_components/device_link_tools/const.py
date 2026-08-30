"""Constants for the Device Link Tools integration."""

import logging

DOMAIN = "device_link_tools"

LOGGER = logging.getLogger(__package__)

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
