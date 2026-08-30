"""The Device Link Tools integration."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportReturnType=false

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .reapply import DeviceLinkReapplier, DeviceLinkToolsConfigEntry
from .services import async_setup_services

CONFIG_SCHEMA: Any = cv.config_entry_only_config_schema(DOMAIN)  # pylint: disable=invalid-name


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001 # pylint: disable=unused-argument
    """Register the device link tools actions.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        config (ConfigType): The configuration dictionary.

    Returns:
        bool: True if setup was successful.

    """
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DeviceLinkToolsConfigEntry) -> bool:
    """Set up device link tools from a config entry.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (DeviceLinkToolsConfigEntry): The config entry to set up.

    Returns:
        bool: True if setup was successful.

    """
    reapplier = DeviceLinkReapplier(hass, entry)
    entry.runtime_data = reapplier
    reapplier.async_setup()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DeviceLinkToolsConfigEntry) -> bool:  # noqa: ARG001 # pylint: disable=unused-argument
    """Unload a config entry.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (DeviceLinkToolsConfigEntry): The config entry to unload.

    Returns:
        bool: True if unload was successful.

    """
    return True
