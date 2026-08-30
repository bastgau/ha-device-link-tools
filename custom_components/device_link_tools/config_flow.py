"""Config and options flow for the Device Link Tools integration."""

# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportReturnType=false

from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    DeviceSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN
from .helpers import async_resolve_device_id
from .reapply import DeviceLinkToolsConfigEntry, async_apply_link, async_stored_links

_DEVICE_SELECTOR: Any = DeviceSelector()
_ENTITY_SELECTOR: Any = EntitySelector(EntitySelectorConfig(multiple=True))

# Failures the add form can report on the field itself; anything else is reported as a
# generic invalid device.
_FORM_ERRORS = {
    "device_id_composite",
    "device_id_unknown",
    "device_is_child",
    "device_without_identifiers",
    "entity_not_registered",
    "entry_not_loaded",
    "link_set_elsewhere",
}


@callback
def _form_error(err: HomeAssistantError) -> str:
    """Return the form error key for a failure raised while linking.

    Args:
        err (HomeAssistantError): The HomeAssistant error raised.

    Returns:
        str: The form error key.

    """
    key = err.translation_key or ""
    return key if key in _FORM_ERRORS else "invalid_device"


class DeviceLinkToolsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Confirmation-only flow: there is nothing to configure."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: DeviceLinkToolsConfigEntry,  # noqa: ARG004
    ) -> OptionsFlowWithReload:
        """Get the options flow for this handler.

        Args:
            config_entry (DeviceLinkToolsConfigEntry): The config entry.

        Returns:
            OptionsFlowWithReload: The options flow instance.

        """
        return DeviceLinkToolsOptionsFlow()

    @override
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        if user_input is not None:
            return self.async_create_entry(title="Device Link Tools", data={})

        return self.async_show_form(step_id="user")


class DeviceLinkToolsOptionsFlow(OptionsFlowWithReload):
    """Manage the recorded links from the UI."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:  # pylint: disable=unused-argument
        """Offer to add or remove a link.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        return self.async_show_menu(step_id="init", menu_options=["add_link", "remove_link"])

    async def async_step_add_link(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Link entities to a picked device.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                device = async_resolve_device_id(self.hass, user_input[ATTR_DEVICE_ID])
                async_apply_link(self.hass, user_input[ATTR_ENTITY_ID], device)
            except HomeAssistantError as err:
                errors["base"] = _form_error(err)
            else:
                # async_apply_link already wrote the options; handing them back
                # unchanged just ends the flow.
                return self.async_create_entry(data=dict(self.config_entry.options))

        return self.async_show_form(
            step_id="add_link",
            data_schema=vol.Schema(
                {
                    vol.Required(ATTR_ENTITY_ID): _ENTITY_SELECTOR,
                    vol.Required(ATTR_DEVICE_ID): _DEVICE_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_link(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Unlink entities from the device they were linked to.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        links = async_stored_links(self.config_entry)
        if not links:
            return self.async_abort(reason="no_links")

        errors: dict[str, str] = {}
        if user_input is not None:
            entity_ids = user_input[ATTR_ENTITY_ID]
            if not entity_ids:
                errors["base"] = "no_entity_selected"
            else:
                async_apply_link(self.hass, entity_ids, None)
                return self.async_create_entry(data=dict(self.config_entry.options))

        selector: Any = SelectSelector(
            SelectSelectorConfig(
                options=sorted(links),
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        return self.async_show_form(
            step_id="remove_link",
            data_schema=vol.Schema({vol.Optional(ATTR_ENTITY_ID, default=[]): selector}),
            errors=errors,
        )
