"""Test the integration refuses to run on a Home Assistant that is too old."""

from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.testing_config.common import MockConfigEntry

from .conftest import DOMAIN

MODULE = f"custom_components.{DOMAIN}"

# The guard compares (MAJOR_VERSION, MINOR_VERSION) against MINIMUM_HA_VERSION, so both
# sides of 2026.9 have to be covered, including the year rollover a plain minor
# comparison would get wrong.
TOO_OLD = [
    pytest.param(2026, 8, id="one-release-before"),
    pytest.param(2026, 1, id="same-year-first-release"),
    pytest.param(2025, 12, id="previous-year-later-minor"),
]
SUPPORTED = [
    pytest.param(2026, 9, id="exactly-the-minimum"),
    pytest.param(2026, 10, id="one-release-after"),
    pytest.param(2027, 1, id="next-year-first-release"),
]


@pytest.mark.parametrize(("major", "minor"), TOO_OLD)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_refused_on_older_core(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    major: int,
    minor: int,
) -> None:
    """Test the actions are not registered on a core without the device registry APIs."""
    with (
        patch(f"{MODULE}.MAJOR_VERSION", major),
        patch(f"{MODULE}.MINOR_VERSION", minor),
    ):
        assert not await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, "add_identifier")
    assert "2026.9 or later" in caplog.text


@pytest.mark.parametrize(("major", "minor"), SUPPORTED)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_allowed_on_supported_core(hass: HomeAssistant, major: int, minor: int) -> None:
    """Test the guard lets a recent enough core through."""
    with (
        patch(f"{MODULE}.MAJOR_VERSION", major),
        patch(f"{MODULE}.MINOR_VERSION", minor),
    ):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "add_identifier")


@pytest.mark.parametrize(("major", "minor"), TOO_OLD)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_setup_refused_on_older_core(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    major: int,
    minor: int,
) -> None:
    """Test the entry reports the version requirement rather than crashing later.

    async_setup already refuses on an old core, so a fresh entry never reaches
    async_setup_entry. A reload of an entry set up while the guard was open does,
    which is what an in-place downgrade would look like -- so the version is only
    patched once the config_entry fixture has loaded the entry for real.
    """
    with (
        patch(f"{MODULE}.MAJOR_VERSION", major),
        patch(f"{MODULE}.MINOR_VERSION", minor),
    ):
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert config_entry.error_reason_translation_key == "unsupported_ha_version"


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_loads_on_the_running_core(hass: HomeAssistant) -> None:
    """Test the guard does not stand in the way of the core the tests run on."""
    entry = MockConfigEntry(domain=DOMAIN, title="Device Link Tools")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "add_identifier")
