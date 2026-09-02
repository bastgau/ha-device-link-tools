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
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.selector import (
    DeviceSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN
from .helpers import (
    Identifiers,
    async_resolve_device,
    async_resolve_device_id,
    device_label,
    format_identifiers,
)
from .reapply import (
    DeviceLinkToolsConfigEntry,
    async_apply_link,
    async_stored_links,
)

_DEVICE_SELECTOR: Any = DeviceSelector()

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
def _async_linkable_entities(hass: HomeAssistant) -> list[str]:
    """Return the entities the add step may offer.

    Only entities linked to nothing, to keep the picker short. A link set elsewhere
    would be refused as ``link_set_elsewhere`` anyway; a link recorded here would be
    accepted, but the picker is long enough without the ones already done.

    The selector validates a submission against ``include_entities``, so leaving a
    recorded link out also rules it out of a submission: re-point one through the
    ``add_identifier`` action, or unlink it first.

    Args:
        hass (HomeAssistant): The Home Assistant instance.

    Returns:
        list[str]: The entity IDs that can be linked from the form.

    """
    return sorted(entry.entity_id for entry in er.async_get(hass).entities.values() if entry.device_id is None)


@callback
def _async_link_options(hass: HomeAssistant, entity_ids: list[str]) -> list[SelectOptionDict]:
    """Return the unlink choices, labelled for a human rather than by entity id.

    A bare entity id says neither what the entity is nor which device it was linked to,
    which is what the choice is actually about. The label carries both, and the value
    stays the entity id the flow unlinks.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        entity_ids (list[str]): The linked entity IDs.

    Returns:
        list[SelectOptionDict]: The options to offer, sorted by label.

    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    options: list[SelectOptionDict] = []

    for entity_id in entity_ids:
        entry = entity_registry.async_get(entity_id)
        name = (entry.name or entry.original_name) if entry else None
        # A recorded link whose device cannot be resolved is still worth unlinking, so
        # fall back to the entity id rather than leaving the choice out.
        device_id = entry.device_id if entry else None
        device = device_registry.async_get(device_id) if device_id else None
        label = f"{name or entity_id} ({device_label(device, device_id)})" if device_id else entity_id
        options.append(SelectOptionDict(value=entity_id, label=label))

    return sorted(options, key=lambda option: option["label"])


@callback
def _async_orphan_options(hass: HomeAssistant, links: dict[str, Identifiers]) -> list[SelectOptionDict]:
    """Return the recorded links whose device cannot be resolved any more.

    Through the same resolution the reapplier uses, so this lists exactly the links it
    keeps failing on: a device that was removed, renamed away from its identifiers, or
    that several devices now answer to. The label carries the identifiers, since there
    is no device left to name.

    Args:
        hass (HomeAssistant): The Home Assistant instance.
        links (dict[str, Identifiers]): The recorded links.

    Returns:
        list[SelectOptionDict]: The options to offer, sorted by label.

    """
    options: list[SelectOptionDict] = []

    for entity_id, identifiers in links.items():
        try:
            async_resolve_device(hass, identifiers)
        except HomeAssistantError:
            options.append(SelectOptionDict(value=entity_id, label=f"{entity_id} ({format_identifiers(identifiers)})"))

    return sorted(options, key=lambda option: option["label"])


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
        return self._async_menu()

    @callback
    def _async_menu(self) -> ConfigFlowResult:
        """Return to the menu, so several links can be managed in one visit.

        ``async_apply_link`` has already written the options by the time a step is
        done, so there is nothing left for ``async_create_entry`` to save: ending the
        flow would only close the dialog after a single change. Hence the explicit
        exit entry, which is now the only way out that is not the dialog's own close.

        Only the entries with something to work on are listed. A step that has nothing
        to offer would otherwise abort onto a dead-end page whose only button closes
        the dialog, losing the visit over a menu entry that should not have been there.

        Returns:
            ConfigFlowResult: The flow result.

        """
        links = async_stored_links(self.config_entry)
        menu_options: list[str] = []
        if _async_linkable_entities(self.hass):
            menu_options.append("add_link")
        if links:
            menu_options.append("remove_link")
        if _async_orphan_options(self.hass, links):
            menu_options.append("remove_orphans")
        menu_options.append("exit")

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_exit(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:  # pylint: disable=unused-argument
        """Close the dialog.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        # The options are already saved; handing them back unchanged just ends the
        # flow without asking for a reload. The empty title is what keeps the frontend
        # from rendering a success page on the way out.
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_add_link(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Link entities to a picked device.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        entity_ids = _async_linkable_entities(self.hass)
        errors: dict[str, str] = {}

        if user_input is not None:
            picked = user_input.get(ATTR_ENTITY_ID)
            device_id = user_input.get(ATTR_DEVICE_ID)
            # Submitting the form empty is how this screen is left without linking
            # anything, the same way the two tick lists are.
            if not picked and not device_id:
                return self._async_menu()
            if not picked or not device_id:
                # Half a form is a mis-click rather than a way out; say which half.
                errors["base"] = "incomplete_link"
            else:
                try:
                    async_apply_link(self.hass, picked, async_resolve_device_id(self.hass, device_id))
                except HomeAssistantError as err:
                    errors["base"] = _form_error(err)
                else:
                    return self._async_menu()

        entity_selector: Any = EntitySelector(EntitySelectorConfig(multiple=True, include_entities=entity_ids))
        schema = vol.Schema(
            {
                # No default: a marker carrying one reads as already filled in to the
                # frontend, which then drops the field's own placeholder. What the user
                # did fill in comes back as a suggested value instead, which repopulates
                # the field without claiming the empty one has a value.
                vol.Optional(ATTR_ENTITY_ID): entity_selector,
                vol.Optional(ATTR_DEVICE_ID): _DEVICE_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="add_link",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
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
            # The menu only offers this step when there is something to unlink, so this
            # is the last link going away between the menu being drawn and this click.
            return self._async_menu()

        if user_input is not None:
            # Ticking nothing is how this screen is left without unlinking anything.
            if entity_ids := user_input[ATTR_ENTITY_ID]:
                async_apply_link(self.hass, entity_ids, None)
            return self._async_menu()

        selector: Any = SelectSelector(
            SelectSelectorConfig(
                options=_async_link_options(self.hass, sorted(links)),
                multiple=True,
                mode=SelectSelectorMode.LIST,
            )
        )
        return self.async_show_form(
            step_id="remove_link",
            data_schema=vol.Schema({vol.Optional(ATTR_ENTITY_ID, default=[]): selector}),
        )

    async def async_step_remove_orphans(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Drop the recorded links whose device no longer resolves.

        Unlinking only: re-pointing one at another device stays with the repair issue
        the reapplier raises for it, which asks for the replacement device.

        Args:
            user_input (dict[str, Any] | None): User input data.

        Returns:
            ConfigFlowResult: The flow result.

        """
        options = _async_orphan_options(self.hass, async_stored_links(self.config_entry))
        if not options:
            # As above: the device came back between the menu being drawn and the click.
            return self._async_menu()

        if user_input is not None:
            # Ticking nothing is how this screen is left without dropping anything.
            if entity_ids := user_input[ATTR_ENTITY_ID]:
                async_apply_link(self.hass, entity_ids, None)
            return self._async_menu()

        selector: Any = SelectSelector(
            SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST)
        )
        return self.async_show_form(
            step_id="remove_orphans",
            data_schema=vol.Schema({vol.Optional(ATTR_ENTITY_ID, default=[]): selector}),
        )
