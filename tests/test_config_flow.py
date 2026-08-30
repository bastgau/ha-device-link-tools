"""Test the Device Link Tools config flow."""

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow(hass: HomeAssistant) -> None:
    """Test the confirmation step creates the entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Device Link Tools"
    assert result["data"] == {}


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_single_instance(hass: HomeAssistant) -> None:
    """Test a second entry is refused."""
    MockConfigEntry(domain=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
