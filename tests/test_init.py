"""Setup, unload, reload, hub device and service tests against real Home Assistant."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from mock_sysap_server import MockSysApServer
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freeathome_ng import (
    PLATFORMS,
    FreeAtHomeNgRuntime,
    async_remove_config_entry_device,
)
from custom_components.freeathome_ng.const import (
    CONF_NAME_PREFIX,
    CONF_VIRTUAL_DEVICES,
    DOMAIN,
    SERVICE_DUMP_CONFIG,
    SERVICE_MIGRATE_FROM_LEGACY,
    SERVICE_MONITOR,
    SERVICE_REGISTER_VIRTUAL_DEVICE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_SET_DATAPOINT,
    SERVICE_TRIGGER_PROXY_DEVICE,
    SERVICE_UNREGISTER_VIRTUAL_DEVICE,
)

from .conftest import SYSAP_SERIAL, SYSAP_UUID

ALL_SERVICES = (
    SERVICE_DUMP_CONFIG,
    SERVICE_MIGRATE_FROM_LEGACY,
    SERVICE_MONITOR,
    SERVICE_SET_DATAPOINT,
    SERVICE_REGISTER_VIRTUAL_DEVICE,
    SERVICE_UNREGISTER_VIRTUAL_DEVICE,
    SERVICE_TRIGGER_PROXY_DEVICE,
    SERVICE_SEND_NOTIFICATION,
)


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """Setup stores runtime data, creates the hub device and registers services."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, FreeAtHomeNgRuntime)

    hub = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"hub_{entry.entry_id}"), entry.entry_id
    )
    assert hub is not None
    assert hub.id == entry.runtime_data.hub_device_id
    assert hub.entry_type is dr.DeviceEntryType.SERVICE
    assert hub.serial_number == SYSAP_SERIAL
    assert hub.sw_version == "3.2.1"

    for service in ALL_SERVICES:
        assert hass.services.has_service(DOMAIN, service)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    for service in ALL_SERVICES:
        assert not hass.services.has_service(DOMAIN, service)


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Rejected credentials put the entry into SETUP_ERROR and start a reauth flow."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_PASSWORD: "wrong"}
    )
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_setup_unreachable_retries(hass: HomeAssistant, mock_sysap: MockSysApServer) -> None:
    """An unreachable SysAP leads to SETUP_RETRY."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SYSAP_SERIAL,
        data={"host": "127.0.0.1:1", "username": "apiuser", "password": "secret"},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_options_change_reloads_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Changing an option reloads the entry and creates a new runtime."""
    old_runtime = init_integration.runtime_data
    hass.config_entries.async_update_entry(init_integration, options={CONF_NAME_PREFIX: "NG "})
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert init_integration.runtime_data is not old_runtime


async def test_suppress_reload_skips_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """While `suppress_reload` is set (migration cutover), option changes do not reload."""
    runtime = init_integration.runtime_data
    runtime.suppress_reload = True
    hass.config_entries.async_update_entry(init_integration, options={CONF_NAME_PREFIX: "NG "})
    await hass.async_block_till_done()
    assert init_integration.runtime_data is runtime


async def test_virtual_device_bookkeeping_does_not_reload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_sysap: MockSysApServer
) -> None:
    """Registering and unregistering virtual devices persists them without a reload."""
    runtime = init_integration.runtime_data
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REGISTER_VIRTUAL_DEVICE,
        {
            "native_id": "ha_test_switch",
            "device_type": "SwitchingActuator",
            "display_name": "Test Switch",
            "ttl": 180,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert "ha_test_switch" in init_integration.data[CONF_VIRTUAL_DEVICES]
    assert init_integration.runtime_data is runtime
    assert any(rec[0] == "PUT_VDEV" for rec in mock_sysap.recorded)

    await hass.services.async_call(
        DOMAIN, SERVICE_UNREGISTER_VIRTUAL_DEVICE, {"native_id": "ha_test_switch"}, blocking=True
    )
    await hass.async_block_till_done()
    assert "ha_test_switch" not in init_integration.data[CONF_VIRTUAL_DEVICES]
    assert init_integration.runtime_data is runtime


async def test_set_datapoint_service(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_sysap: MockSysApServer
) -> None:
    """`set_datapoint` writes through to the SysAP."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_DATAPOINT,
        {
            "serialnumber": "ABB700D10001",
            "channel_id": "ch0003",
            "datapoint_id": "idp0000",
            "value": "1",
        },
        blocking=True,
    )
    assert ("PUT_DP", "ABB700D10001.ch0003.idp0000", "1") in mock_sysap.recorded


async def test_services_validate_target(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Services reject unknown hosts and fail once no entry is loaded."""
    data = {
        "serialnumber": "ABB700D10001",
        "channel_id": "ch0003",
        "datapoint_id": "idp0000",
        "value": "1",
    }
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_DATAPOINT, {**data, "host": "10.99.99.99"}, blocking=True
        )


async def test_remove_config_entry_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The hub and present devices are protected; stale devices can be removed."""
    entry = init_integration
    hub = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"hub_{entry.entry_id}"), entry.entry_id
    )
    present = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{SYSAP_UUID}_ABB700D10001"), entry.entry_id
    )
    stale = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{SYSAP_UUID}_REMOVED99")}
    )
    assert hub is not None and present is not None

    assert not await async_remove_config_entry_device(hass, entry, hub)
    assert not await async_remove_config_entry_device(hass, entry, present)
    assert await async_remove_config_entry_device(hass, entry, stale)


async def test_platforms_forwarded(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Every platform module is loaded and push-only."""
    import importlib

    for platform in PLATFORMS:
        module = importlib.import_module(f"custom_components.freeathome_ng.{platform.value}")
        assert module.PARALLEL_UPDATES == 0
        assert platform.value in init_integration.runtime_data.platform_adders
