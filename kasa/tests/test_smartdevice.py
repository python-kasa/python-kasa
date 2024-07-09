"""Tests for SMART devices."""

from __future__ import annotations

import logging
from typing import Any, cast
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from kasa import Device, KasaException, Module
from kasa.exceptions import SmartErrorCode
from kasa.smart import SmartDevice

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
async def test_update_module_errors(dev: SmartDevice, mocker: MockerFixture):
    """Test that modules that error are disabled / removed."""
    # We need to have some modules initialized by now
    assert dev._modules

    critical_modules = {Module.DeviceModule, Module.ChildDevice}
    not_disabling_modules = {Module.Cloud}

    new_dev = SmartDevice("127.0.0.1", protocol=dev.protocol)

    module_queries = {
        modname: q
        for modname, module in dev._modules.items()
        if (q := module.query()) and modname not in critical_modules
    }
    child_module_queries = {
        modname: q
        for child in dev.children
        for modname, module in child._modules.items()
        if (q := module.query()) and modname not in critical_modules
    }
    all_queries_names = {
        key for mod_query in module_queries.values() for key in mod_query
    }
    all_child_queries_names = {
        key for mod_query in child_module_queries.values() for key in mod_query
    }

    async def _query(request, *args, **kwargs):
        responses = await dev.protocol._query(request, *args, **kwargs)
        for k in responses:
            if k in all_queries_names:
                responses[k] = SmartErrorCode.PARAMS_ERROR
        return responses

    async def _child_query(self, request, *args, **kwargs):
        responses = await child_protocols[self._device_id]._query(
            request, *args, **kwargs
        )
        for k in responses:
            if k in all_child_queries_names:
                responses[k] = SmartErrorCode.PARAMS_ERROR
        return responses

    mocker.patch.object(new_dev.protocol, "query", side_effect=_query)

    from kasa.smartprotocol import _ChildProtocolWrapper

    child_protocols = {
        cast(_ChildProtocolWrapper, child.protocol)._device_id: child.protocol
        for child in dev.children
    }
    # children not created yet so cannot patch.object
    mocker.patch("kasa.smartprotocol._ChildProtocolWrapper.query", new=_child_query)

    await new_dev.update()
    for modname in module_queries:
        no_disable = modname in not_disabling_modules
        mod_present = modname in new_dev._modules
        assert (
            mod_present is no_disable
        ), f"{modname} present {mod_present} when no_disable {no_disable}"

    for modname in child_module_queries:
        no_disable = modname in not_disabling_modules
        mod_present = any(modname in child._modules for child in new_dev.children)
        assert (
            mod_present is no_disable
        ), f"{modname} present {mod_present} when no_disable {no_disable}"


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
