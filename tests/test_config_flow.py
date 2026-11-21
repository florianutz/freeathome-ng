"""Tests for free@home NG config, discovery, reauth, reconfigure, and options flows."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from types import SimpleNamespace
from unittest.mock import AsyncMock

import freeathome_ng.config_flow as config_flow_mod
import pytest
from freeathome_ng.api.client import FreeAtHomeLocalApiClient
from freeathome_ng.config_flow import (
    FreeAtHomeNgConfigFlow,
    FreeAtHomeNgOptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from mock_sysap_server import MockSysApServer


def _make_hass(entries: list[SimpleNamespace] | None = None) -> SimpleNamespace:
    stored = list(entries or [])

    def _async_entries(_domain: str | None = None) -> list[SimpleNamespace]:
        return stored

    def _async_get_entry(entry_id: str) -> SimpleNamespace | None:
        return next((e for e in stored if e.entry_id == entry_id), None)

    return SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=_async_entries,
            async_get_entry=_async_get_entry,
        )
    )


async def test_user_flow_success_errors_and_duplicate() -> None:
    """Verify manual setup happy path, username resolution, errors, and duplicate abort."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass = _make_hass()
        flow = FreeAtHomeNgConfigFlow()
        flow.hass = hass

        initial = await flow.async_step_user()
        assert initial["type"] == "form"
        assert initial["step_id"] == "user"

        bad_auth = await flow.async_step_user(
            {
                CONF_HOST: server.host_port,
                CONF_USERNAME: "apiuser",
                CONF_PASSWORD: "wrong",
            }
        )
        assert bad_auth["type"] == "form"
        assert bad_auth["errors"] == {"base": "invalid_auth"}

        cannot_connect = await flow.async_step_user(
            {
                CONF_HOST: "127.0.0.1:1",
                CONF_USERNAME: "apiuser",
                CONF_PASSWORD: "secret",
            }
        )
        assert cannot_connect["type"] == "form"
        assert cannot_connect["errors"] == {"base": "cannot_connect"}

        created = await flow.async_step_user(
            {
                CONF_HOST: server.host_port,
                CONF_USERNAME: "installer",
                CONF_PASSWORD: "secret",
            }
        )
        assert created["type"] == "create_entry"
        assert created["title"] == "Test SysAP"
        assert created["data"][CONF_USERNAME] == "apiuser"

        existing = SimpleNamespace(
            entry_id="e1",
            unique_id="ABB700999999",
            data={CONF_HOST: server.host_port},
            options={},
        )
        dup_flow = FreeAtHomeNgConfigFlow()
        dup_flow.hass = _make_hass([existing])
        with pytest.raises(AbortFlow) as exc_info:
            await dup_flow.async_step_user(
                {
                    CONF_HOST: server.host_port,
                    CONF_USERNAME: "apiuser",
                    CONF_PASSWORD: "secret",
                }
            )
        assert exc_info.value.reason == "already_configured"
    finally:
        await server.stop()


async def test_zeroconf_and_link_flows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify Zeroconf discovery filtering, host update abort, and link completion."""
    flow = FreeAtHomeNgConfigFlow()
    flow.hass = _make_hass()

    ipv6_res = await flow.async_step_zeroconf(
        ZeroconfServiceInfo(
            ip_address=IPv6Address("::1"),
            name="free@home SysAP._http._tcp.local.",
        )
    )
    assert ipv6_res["type"] == "abort"
    assert ipv6_res["reason"] == "not_ipv4address"

    monkeypatch.setattr(
        FreeAtHomeLocalApiClient,
        "fetch_settings_json",
        AsyncMock(return_value=None),
    )
    not_sysap = await flow.async_step_zeroconf(
        ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.50"),
            name="free@home SysAP._http._tcp.local.",
        )
    )
    assert not_sysap["type"] == "abort"
    assert not_sysap["reason"] == "not_sysap"

    monkeypatch.setattr(
        FreeAtHomeLocalApiClient,
        "fetch_settings_json",
        AsyncMock(return_value={"flags": {}}),
    )
    no_serial = await flow.async_step_zeroconf(
        ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.50"),
            name="free@home SysAP._http._tcp.local.",
        )
    )
    assert no_serial["type"] == "abort"
    assert no_serial["reason"] == "serialNumber_not_found"

    monkeypatch.setattr(
        FreeAtHomeLocalApiClient,
        "fetch_settings_json",
        AsyncMock(return_value={"flags": {"serialNumber": "ABB700999999"}}),
    )
    link_form = await flow.async_step_zeroconf(
        ZeroconfServiceInfo(
            ip_address=IPv4Address("192.168.1.50"),
            name="Busch-Jaeger:Living SysAP._http._tcp.local.",
        )
    )
    assert link_form["type"] == "form"
    assert link_form["step_id"] == "link"

    monkeypatch.setattr(
        config_flow_mod,
        "validate_input",
        AsyncMock(
            return_value={
                "title": "Living SysAP",
                "serial_number": "ABB700999999",
                "sysap_uuid": "00000000-0000-0000-0000-000000000000",
                "resolved_username": "apiuser",
            }
        ),
    )
    created = await flow.async_step_link(
        {CONF_USERNAME: "installer", CONF_PASSWORD: "secret"}
    )
    assert created["type"] == "create_entry"
    assert created["title"] == "Living SysAP"
    assert created["data"][CONF_HOST] == "192.168.1.50"
    assert created["data"][CONF_USERNAME] == "apiuser"

    existing = SimpleNamespace(
        entry_id="e1",
        unique_id="ABB700999999",
        data={CONF_HOST: "192.168.1.10"},
        options={},
    )
    dup_flow = FreeAtHomeNgConfigFlow()
    dup_flow.hass = _make_hass([existing])
    with pytest.raises(AbortFlow) as exc_info:
        await dup_flow.async_step_zeroconf(
            ZeroconfServiceInfo(
                ip_address=IPv4Address("192.168.1.55"),
                name="free@home SysAP._http._tcp.local.",
            )
        )
    assert exc_info.value.reason == "already_configured"
    assert existing.data[CONF_HOST] == "192.168.1.55"


async def test_reauth_and_reconfigure_use_update_and_abort() -> None:
    """Verify reauth and reconfigure call async_update_and_abort and guard SysAP identity."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        entry = SimpleNamespace(
            entry_id="entry_1",
            unique_id="ABB700999999",
            data={
                CONF_HOST: server.host_port,
                CONF_USERNAME: "apiuser",
                CONF_PASSWORD: "old",
            },
            options={},
        )
        hass = _make_hass([entry])

        # Reauth flow
        reauth_flow = FreeAtHomeNgConfigFlow()
        reauth_flow.hass = hass
        reauth_flow.context = {"entry_id": "entry_1"}

        called_methods: list[str] = []
        orig_update_and_abort = reauth_flow.async_update_and_abort

        def _spy_update_and_abort(*args, **kwargs):
            called_methods.append("async_update_and_abort")
            return orig_update_and_abort(*args, **kwargs)

        def _forbid_reload_and_abort(*_args, **_kwargs):
            raise AssertionError("async_update_reload_and_abort must not be called")

        reauth_flow.async_update_and_abort = _spy_update_and_abort  # type: ignore[method-assign]
        reauth_flow.async_update_reload_and_abort = _forbid_reload_and_abort  # type: ignore[method-assign]

        form = await reauth_flow.async_step_reauth(entry.data)
        assert form["step_id"] == "reauth_confirm"

        bad = await reauth_flow.async_step_reauth_confirm(
            {CONF_USERNAME: "apiuser", CONF_PASSWORD: "wrong"}
        )
        assert bad["errors"] == {"base": "invalid_auth"}

        ok = await reauth_flow.async_step_reauth_confirm(
            {CONF_USERNAME: "installer", CONF_PASSWORD: "secret"}
        )
        assert ok["type"] == "abort"
        assert ok["reason"] == "reauth_successful"
        assert called_methods == ["async_update_and_abort"]
        assert entry.data[CONF_USERNAME] == "apiuser"
        assert entry.data[CONF_PASSWORD] == "secret"

        # Reconfigure flow: mismatch serial -> other_sysap
        entry_wrong_serial = SimpleNamespace(
            entry_id="entry_2",
            unique_id="ABB700OTHER",
            data={
                CONF_HOST: server.host_port,
                CONF_USERNAME: "apiuser",
                CONF_PASSWORD: "secret",
            },
            options={},
        )
        hass2 = _make_hass([entry, entry_wrong_serial])
        reconf_flow = FreeAtHomeNgConfigFlow()
        reconf_flow.hass = hass2
        reconf_flow.context = {"entry_id": "entry_2"}
        mismatch = await reconf_flow.async_step_reconfigure(
            {CONF_HOST: server.host_port, "name_prefix": "NG "}
        )
        assert mismatch["type"] == "form"
        assert mismatch["errors"] == {CONF_HOST: "other_sysap"}

        # Reconfigure flow: matching serial -> async_update_and_abort
        called_reconf: list[str] = []
        reconf_ok_flow = FreeAtHomeNgConfigFlow()
        reconf_ok_flow.hass = hass2
        reconf_ok_flow.context = {"entry_id": "entry_1"}
        orig_reconf_abort = reconf_ok_flow.async_update_and_abort
        reconf_ok_flow.async_update_and_abort = (  # type: ignore[method-assign]
            lambda *a, **kw: (
                called_reconf.append("async_update_and_abort"),
                orig_reconf_abort(*a, **kw),
            )[1]
        )
        reconf_ok_flow.async_update_reload_and_abort = _forbid_reload_and_abort  # type: ignore[method-assign]

        reconf_res = await reconf_ok_flow.async_step_reconfigure(
            {CONF_HOST: server.host_port, "name_prefix": "NG "}
        )
        assert reconf_res["type"] == "abort"
        assert reconf_res["reason"] == "reconfigure_successful"
        assert called_reconf == ["async_update_and_abort"]
        assert entry.data["name_prefix"] == "NG "
    finally:
        await server.stop()


async def test_options_flow_zero_arg_init() -> None:
    """Verify OptionsFlow initializes without arguments and reads self.config_entry."""
    entry = SimpleNamespace(
        entry_id="entry_1",
        data={CONF_HOST: "192.168.1.50", "use_room_names": False},
        options={"name_prefix": "NG "},
    )
    options_flow = FreeAtHomeNgConfigFlow.async_get_options_flow(entry)  # type: ignore[arg-type]
    assert isinstance(options_flow, FreeAtHomeNgOptionsFlow)
    options_flow.config_entry = entry

    form = await options_flow.async_step_init()
    assert form["type"] == "form"
    assert form["step_id"] == "init"

    saved = await options_flow.async_step_init(
        {"use_room_names": True, "name_prefix": "Test "}
    )
    assert saved["type"] == "create_entry"
    assert saved["data"] == {"use_room_names": True, "name_prefix": "Test "}
