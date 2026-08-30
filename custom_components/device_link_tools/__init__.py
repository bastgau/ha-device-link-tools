"""The Device Link Tools integration."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportReturnType=false

from typing import Any

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION, __version__
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER, MINIMUM_HA_VERSION
from .reapply import DeviceLinkReapplier, DeviceLinkToolsConfigEntry
from .services import async_setup_services

CONFIG_SCHEMA: Any = cv.config_entry_only_config_schema(DOMAIN)  # pylint: disable=invalid-name

_MINIMUM_HA_VERSION_STR = f"{MINIMUM_HA_VERSION[0]}.{MINIMUM_HA_VERSION[1]}"


def _core_is_supported() -> bool:
    """Return whether the running core has the device registry APIs this integration needs.

    Returns:
        bool: True if the core is recent enough.

    """
    return (MAJOR_VERSION, MINOR_VERSION) >= MINIMUM_HA_VERSION


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001 # pylint: disable=unused-argument
    """Register the device link tools actions.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        config (ConfigType): The configuration dictionary.

    Returns:
        bool: True if setup was successful.

    """
    if not _core_is_supported():
        # Registering the actions anyway would only trade this one clear log line for a
        # TypeError from the device registry the first time one of them is called.
        LOGGER.error(
            "Device Link Tools needs Home Assistant %s or later, but this is %s. "
            "The actions were not registered; upgrade Home Assistant",
            _MINIMUM_HA_VERSION_STR,
            __version__,
        )
        return False

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DeviceLinkToolsConfigEntry) -> bool:
    """Set up device link tools from a config entry.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entry (DeviceLinkToolsConfigEntry): The config entry to set up.

    Returns:
        bool: True if setup was successful.

    Raises:
        ConfigEntryError: If the running Home Assistant is older than the minimum.

    """
    if not _core_is_supported():
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="unsupported_ha_version",
            translation_placeholders={
                "minimum_version": _MINIMUM_HA_VERSION_STR,
                "version": __version__,
            },
        )

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
    # Nothing to tear down by hand: the reapplier registers both of its listeners
    # through entry.async_on_unload, and Home Assistant drops runtime_data itself.
    return True
