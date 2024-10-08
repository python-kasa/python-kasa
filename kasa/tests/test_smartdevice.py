"""Tests for SMART devices."""

from __future__ import annotations

import logging
import time
from typing import Any, cast
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_mock import MockerFixture

from kasa import Device, KasaException, Module
from kasa.exceptions import DeviceError, SmartErrorCode
from kasa.smart import SmartDevice
from kasa.smart.modules.energy import Energy
from kasa.smart.smartmodule import SmartModule
from kasa.smartprotocol import _ChildProtocolWrapper

from .conftest import (
    device_smart,
    get_device_for_fixture_protocol,
    get_parent_and_child_modules,
)


@device_smart
async def test_try_get_response(dev: SmartDevice, caplog):
    mock_response: dict = {
        "get_device_info": SmartErrorCode.PARAMS_ERROR,
    }
    caplog.set_level(logging.DEBUG)
    dev._try_get_response(mock_response, "get_device_info", {})
    msg = "Error PARAMS_ERROR(-1008) getting request get_device_info for device 127.0.0.123"
    assert msg in caplog.text


@device_smart
async def test_update_no_device_info(dev: SmartDevice, mocker: MockerFixture):
    mock_response: dict = {
        "get_device_usage": {},
        "get_device_time": {},
    }
    msg = f"get_device_info not found in {mock_response} for device 127.0.0.123"
    with (
        mocker.patch.object(dev.protocol, "query", return_value=mock_response),
        pytest.raises(KasaException, match=msg),
    ):
        await dev.update()


@device_smart
async def test_initial_update(dev: SmartDevice, mocker: MockerFixture):
    """Test the initial update cycle."""
    # As the fixture data is already initialized, we reset the state for testing
    dev._components_raw = None
    dev._components = {}
    dev._modules = {}
    dev._features = {}
    dev._children = {}
    dev._last_update = {}
    dev._last_update_time = None

    negotiate = mocker.spy(dev, "_negotiate")
    initialize_modules = mocker.spy(dev, "_initialize_modules")
    initialize_features = mocker.spy(dev, "_initialize_features")

    # Perform two updates and verify that initialization is only done once
    await dev.update()
    await dev.update()

    negotiate.assert_called_once()
    assert dev._components_raw is not None
    initialize_modules.assert_called_once()
    assert dev.modules
    initialize_features.assert_called_once()
    assert dev.features


@device_smart
async def test_negotiate(dev: SmartDevice, mocker: MockerFixture):
    """Test that the initial negotiation performs expected steps."""
    # As the fixture data is already initialized, we reset the state for testing
    dev._components_raw = None
    dev._children = {}

    query = mocker.spy(dev.protocol, "query")
    initialize_children = mocker.spy(dev, "_initialize_children")
    await dev._negotiate()

    # Check that we got the initial negotiation call
    query.assert_any_call(
        {
            "component_nego": None,
            "get_device_info": None,
            "get_connect_cloud_state": None,
        }
    )
    assert dev._components_raw

    # Check the children are created, if device supports them
    if "child_device" in dev._components:
        initialize_children.assert_called_once()
        query.assert_any_call(
            {
                "get_child_device_component_list": None,
                "get_child_device_list": None,
            }
        )
        assert len(dev._children) == dev.internal_state["get_child_device_list"]["sum"]


@device_smart
async def test_update_module_queries(dev: SmartDevice, mocker: MockerFixture):
    """Test that the regular update uses queries from all supported modules."""
    # We need to have some modules initialized by now
    assert dev._modules
    # Reset last update so all modules will query
    for mod in dev._modules.values():
        mod._last_update_time = None

    device_queries: dict[SmartDevice, dict[str, Any]] = {}
    for mod in dev._modules.values():
        device_queries.setdefault(mod._device, {}).update(mod.query())
    # Hubs do not query child modules by default.
    if dev.device_type != Device.Type.Hub:
        for child in dev.children:
            for mod in child.modules.values():
                device_queries.setdefault(mod._device, {}).update(mod.query())

    spies = {}
    for device in device_queries:
        spies[device] = mocker.spy(device.protocol, "query")

    await dev.update()
    for device in device_queries:
        if device_queries[device]:
            # Need assert any here because the child device updates use the parent's protocol
            spies[device].assert_any_call(device_queries[device])
        else:
            spies[device].assert_not_called()


@device_smart
async def test_update_module_update_delays(
    dev: SmartDevice,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
):
    """Test that modules with minimum delays delay."""
    # We need to have some modules initialized by now
    assert dev._modules

    new_dev = SmartDevice("127.0.0.1", protocol=dev.protocol)
    await new_dev.update()
    first_update_time = time.monotonic()
    assert new_dev._last_update_time == first_update_time
    for module in new_dev.modules.values():
        if module.query():
            assert module._last_update_time == first_update_time

    seconds = 0
    tick = 30
    while seconds <= 180:
        seconds += tick
        freezer.tick(tick)

        now = time.monotonic()
        await new_dev.update()
        for module in new_dev.modules.values():
            mod_delay = module.MINIMUM_UPDATE_INTERVAL_SECS
            if module.query():
                expected_update_time = (
                    now if mod_delay == 0 else now - (seconds % mod_delay)
                )

                assert (
                    module._last_update_time == expected_update_time
                ), f"Expected update time {expected_update_time} after {seconds} seconds for {module.name} with delay {mod_delay} got {module._last_update_time}"


@pytest.mark.parametrize(
    ("first_update"),
    [
        pytest.param(True, id="First update true"),
        pytest.param(False, id="First update false"),
    ],
)
@pytest.mark.parametrize(
    ("error_type"),
    [
        pytest.param(SmartErrorCode.PARAMS_ERROR, id="Device error"),
        pytest.param(TimeoutError("Dummy timeout"), id="Query error"),
    ],
)
@pytest.mark.parametrize(
    ("recover"),
    [
        pytest.param(True, id="recover"),
        pytest.param(False, id="no recover"),
    ],
)
@device_smart
async def test_update_module_query_errors(
    dev: SmartDevice,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
    first_update,
    error_type,
    recover,
):
    """Test that modules that disabled / removed on query failures.

    i.e. the whole query times out rather than device returns an error.
    """
    # We need to have some modules initialized by now
    assert dev._modules

    SmartModule.DISABLE_AFTER_ERROR_COUNT = 2
    first_update_queries = {"get_device_info", "get_connect_cloud_state"}

    critical_modules = {Module.DeviceModule, Module.ChildDevice}

    new_dev = SmartDevice("127.0.0.1", protocol=dev.protocol)
    if not first_update:
        await new_dev.update()
        freezer.tick(
            max(module.MINIMUM_UPDATE_INTERVAL_SECS for module in dev._modules.values())
        )

    module_queries = {
        modname: q
        for modname, module in dev._modules.items()
        if (q := module.query()) and modname not in critical_modules
    }

    async def _query(request, *args, **kwargs):
        if (
            "component_nego" in request
            or "get_child_device_component_list" in request
            or "control_child" in request
        ):
            resp = await dev.protocol._query(request, *args, **kwargs)
            resp["get_connect_cloud_state"] = SmartErrorCode.CLOUD_FAILED_ERROR
            return resp
        # Don't test for errors on get_device_info as that is likely terminal
        if len(request) == 1 and "get_device_info" in request:
            return await dev.protocol._query(request, *args, **kwargs)

        if isinstance(error_type, SmartErrorCode):
            if len(request) == 1:
                raise DeviceError("Dummy device error", error_code=error_type)
            raise TimeoutError("Dummy timeout")
        raise error_type

    child_protocols = {
        cast(_ChildProtocolWrapper, child.protocol)._device_id: child.protocol
        for child in dev.children
    }

    async def _child_query(self, request, *args, **kwargs):
        return await child_protocols[self._device_id]._query(request, *args, **kwargs)

    mocker.patch.object(new_dev.protocol, "query", side_effect=_query)
    # children not created yet so cannot patch.object
    mocker.patch("kasa.smartprotocol._ChildProtocolWrapper.query", new=_child_query)

    await new_dev.update()

    msg = f"Error querying {new_dev.host} for modules"
    assert msg in caplog.text
    for modname in module_queries:
        mod = cast(SmartModule, new_dev.modules[modname])
        assert mod.disabled is False, f"{modname} disabled"
        assert mod.update_interval == mod.UPDATE_INTERVAL_AFTER_ERROR_SECS
        for mod_query in module_queries[modname]:
            if not first_update or mod_query not in first_update_queries:
                msg = f"Error querying {new_dev.host} individually for module query '{mod_query}"
                assert msg in caplog.text

    # Query again should not run for the modules
    caplog.clear()
    await new_dev.update()
    for modname in module_queries:
        mod = cast(SmartModule, new_dev.modules[modname])
        assert mod.disabled is False, f"{modname} disabled"

    freezer.tick(SmartModule.UPDATE_INTERVAL_AFTER_ERROR_SECS)

    caplog.clear()

    if recover:
        mocker.patch.object(
            new_dev.protocol, "query", side_effect=new_dev.protocol._query
        )
        mocker.patch(
            "kasa.smartprotocol._ChildProtocolWrapper.query",
            new=_ChildProtocolWrapper._query,
        )

    await new_dev.update()
    msg = f"Error querying {new_dev.host} for modules"
    if not recover:
        assert msg in caplog.text
    for modname in module_queries:
        mod = cast(SmartModule, new_dev.modules[modname])
        if not recover:
            assert mod.disabled is True, f"{modname} not disabled"
            assert mod._error_count == 2
            assert mod._last_update_error
            for mod_query in module_queries[modname]:
                if not first_update or mod_query not in first_update_queries:
                    msg = f"Error querying {new_dev.host} individually for module query '{mod_query}"
                    assert msg in caplog.text
            # Test one of the raise_if_update_error
            if mod.name == "Energy":
                emod = cast(Energy, mod)
                with pytest.raises(KasaException, match="Module update error"):
                    assert emod.current_consumption is not None
        else:
            assert mod.disabled is False
            assert mod._error_count == 0
            assert mod._last_update_error is None
            # Test one of the raise_if_update_error doesn't raise
            if mod.name == "Energy":
                emod = cast(Energy, mod)
                assert emod.current_consumption is not None


async def test_get_modules():
    """Test getting modules for child and parent modules."""
    dummy_device = await get_device_for_fixture_protocol(
        "KS240(US)_1.0_1.0.5.json", "SMART"
    )
    from kasa.smart.modules import Cloud

    # Modules on device
    module = dummy_device.modules.get("Cloud")
    assert module
    assert module._device == dummy_device
    assert isinstance(module, Cloud)

    module = dummy_device.modules.get(Module.Cloud)
    assert module
    assert module._device == dummy_device
    assert isinstance(module, Cloud)

    # Modules on child
    module = dummy_device.modules.get("Fan")
    assert module is None
    module = next(get_parent_and_child_modules(dummy_device, "Fan"))
    assert module
    assert module._device != dummy_device
    assert module._device._parent == dummy_device

    # Invalid modules
    module = dummy_device.modules.get("DummyModule")
    assert module is None

    module = dummy_device.modules.get(Module.IotAmbientLight)
    assert module is None


@device_smart
async def test_smartdevice_cloud_connection(dev: SmartDevice, mocker: MockerFixture):
    """Test is_cloud_connected property."""
    assert isinstance(dev, SmartDevice)
    assert "cloud_connect" in dev._components

    is_connected = (
        (cc := dev._last_update.get("get_connect_cloud_state"))
        and not isinstance(cc, SmartErrorCode)
        and cc["status"] == 0
    )

    assert dev.is_cloud_connected == is_connected
    last_update = dev._last_update

    for child in dev.children:
        mocker.patch.object(child.protocol, "query", return_value=child._last_update)

    last_update["get_connect_cloud_state"] = {"status": 0}
    with patch.object(dev.protocol, "query", return_value=last_update):
        await dev.update()
        assert dev.is_cloud_connected is True

    last_update["get_connect_cloud_state"] = {"status": 1}
    with patch.object(dev.protocol, "query", return_value=last_update):
        await dev.update()
        assert dev.is_cloud_connected is False

    last_update["get_connect_cloud_state"] = SmartErrorCode.UNKNOWN_METHOD_ERROR
    with patch.object(dev.protocol, "query", return_value=last_update):
        await dev.update()
        assert dev.is_cloud_connected is False

    # Test for no cloud_connect component during device initialisation
    component_list = [
        val
        for val in dev._components_raw["component_list"]
        if val["id"] not in {"cloud_connect"}
    ]
    initial_response = {
        "component_nego": {"component_list": component_list},
        "get_connect_cloud_state": last_update["get_connect_cloud_state"],
        "get_device_info": last_update["get_device_info"],
    }

    new_dev = SmartDevice("127.0.0.1", protocol=dev.protocol)

    first_call = True

    async def side_effect_func(*args, **kwargs):
        nonlocal first_call
        resp = (
            initial_response
            if first_call
            else await new_dev.protocol._query(*args, **kwargs)
        )
        first_call = False
        return resp

    with patch.object(
        new_dev.protocol,
        "query",
        side_effect=side_effect_func,
    ):
        await new_dev.update()
        assert new_dev.is_cloud_connected is False
