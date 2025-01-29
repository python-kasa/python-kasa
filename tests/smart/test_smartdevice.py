"""Tests for SMART devices."""

from __future__ import annotations

import copy
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_mock import MockerFixture

from kasa import Device, DeviceType, KasaException, Module
from kasa.exceptions import DeviceError, SmartErrorCode
from kasa.smart import SmartDevice
from kasa.smart.modules.energy import Energy
from kasa.smart.smartmodule import SmartModule
from kasa.smartcam import SmartCamDevice
from tests.conftest import (
    DISCOVERY_MOCK_IP,
    device_smart,
    get_device_for_fixture_protocol,
    get_parent_and_child_modules,
    smart_discovery,
)
from tests.device_fixtures import (
    hub_smartcam,
    hubs_smart,
    parametrize_combine,
    variable_temp_smart,
)

from ..fakeprotocol_smart import FakeSmartTransport
from ..fakeprotocol_smartcam import FakeSmartCamTransport

DUMMY_CHILD_REQUEST_PREFIX = "get_dummy_"

hub_all = parametrize_combine([hubs_smart, hub_smartcam])


@device_smart
@pytest.mark.requires_dummy
@pytest.mark.xdist_group(name="caplog")
async def test_try_get_response(dev: SmartDevice, caplog):
    mock_response: dict = {
        "get_device_info": SmartErrorCode.PARAMS_ERROR,
    }
    caplog.set_level(logging.DEBUG)
    dev._try_get_response(mock_response, "get_device_info", {})
    msg = "Error PARAMS_ERROR(-1008) getting request get_device_info for device 127.0.0.123"
    assert msg in caplog.text


@device_smart
@pytest.mark.requires_dummy
async def test_update_no_device_info(dev: SmartDevice, mocker: MockerFixture):
    mock_response: dict = {
        "get_device_usage": {},
        "get_device_time": {},
    }
    msg = f"get_device_info not found in {mock_response} for device 127.0.0.123"
    mocker.patch.object(dev.protocol, "query", return_value=mock_response)
    with pytest.raises(KasaException, match=msg):
        await dev.update()


@smart_discovery
async def test_device_type_no_update(discovery_mock, caplog: pytest.LogCaptureFixture):
    """Test device type and repr when device not updated."""
    dev = SmartDevice(DISCOVERY_MOCK_IP)
    assert dev.device_type is DeviceType.Unknown
    assert repr(dev) == f"<DeviceType.Unknown at {DISCOVERY_MOCK_IP} - update() needed>"

    discovery_result = copy.deepcopy(discovery_mock.discovery_data["result"])

    disco_model = discovery_result["device_model"]
    short_model, _, _ = disco_model.partition("(")
    dev.update_from_discover_info(discovery_result)
    assert dev.device_type is DeviceType.Unknown
    assert (
        repr(dev)
        == f"<DeviceType.Unknown at {DISCOVERY_MOCK_IP} - None ({short_model}) - update() needed>"
    )
    discovery_result["device_type"] = "SMART.FOOBAR"
    dev.update_from_discover_info(discovery_result)
    dev._components = {"dummy": 1}
    assert dev.device_type is DeviceType.Plug
    assert (
        repr(dev)
        == f"<DeviceType.Plug at {DISCOVERY_MOCK_IP} - None ({short_model}) - update() needed>"
    )
    assert "Unknown device type, falling back to plug" in caplog.text


@device_smart
async def test_initial_update(dev: SmartDevice, mocker: MockerFixture):
    """Test the initial update cycle."""
    # As the fixture data is already initialized, we reset the state for testing
    dev._components_raw = None
    dev._components = {}
    dev._modules = OrderedDict()
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
        await dev.update()
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
@pytest.mark.xdist_group(name="caplog")
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

                assert module._last_update_time == expected_update_time, (
                    f"Expected update time {expected_update_time} after {seconds} seconds for {module.name} with delay {mod_delay} got {module._last_update_time}"
                )


async def _get_child_responses(child_requests: list[dict[str, Any]], child_protocol):
    """Get dummy responses for testing all child modules.

    Even if they don't return really return query.
    """
    child_req = {item["method"]: item.get("params") for item in child_requests}
    child_resp = {k: v for k, v in child_req.items() if k.startswith("get_dummy")}
    child_req = {
        k: v for k, v in child_req.items() if k.startswith("get_dummy") is False
    }
    resp = await child_protocol._query(child_req)
    resp = {**child_resp, **resp}
    return [
        {"method": k, "error_code": 0, "result": v or {"dummy": "dummy"}}
        for k, v in resp.items()
    ]


@hub_all
@pytest.mark.xdist_group(name="caplog")
async def test_hub_children_update_delays(
    dev: SmartDevice,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    freezer: FrozenDateTimeFactory,
):
    """Test that hub children use the correct delay."""
    if not dev.children:
        pytest.skip(f"Device {dev.model} does not have children.")
    # We need to have some modules initialized by now
    assert dev._modules

    new_dev = type(dev)("127.0.0.1", protocol=dev.protocol)
    module_queries: dict[str, dict[str, dict]] = {}

    # children should always update on first update
    await new_dev.update(update_children=False)

    if TYPE_CHECKING:
        from ..fakeprotocol_smart import FakeSmartTransport

        assert isinstance(dev.protocol._transport, FakeSmartTransport)
    if dev.protocol._transport.child_protocols:
        for child in new_dev.children:
            for modname, module in child._modules.items():
                if (
                    not (q := module.query())
                    and modname not in {"DeviceModule", "Light", "Battery", "Camera"}
                    and not module.SYSINFO_LOOKUP_KEYS
                ):
                    q = {f"get_dummy_{modname}": {}}
                    mocker.patch.object(module, "query", return_value=q)
                if q:
                    queries = module_queries.setdefault(child.device_id, {})
                    queries[cast(str, modname)] = q
                module._last_update_time = None

    module_queries[""] = {
        cast(str, modname): q
        for modname, module in dev._modules.items()
        if (q := module.query())
    }

    async def _query(request, *args, **kwargs):
        # If this is a child multipleRequest query return the error wrapped
        child_id = None
        # smart hub
        if (
            (cc := request.get("control_child"))
            and (child_id := cc.get("device_id"))
            and (requestData := cc["requestData"])
            and requestData["method"] == "multipleRequest"
            and (child_requests := requestData["params"]["requests"])
        ):
            child_protocol = dev.protocol._transport.child_protocols[child_id]
            resp = await _get_child_responses(child_requests, child_protocol)
            return {"control_child": {"responseData": {"result": {"responses": resp}}}}
        # smartcam hub
        if (
            (mr := request.get("multipleRequest"))
            and (requests := mr.get("requests"))
            # assumes all requests for the same child
            and (
                child_id := next(iter(requests))
                .get("params", {})
                .get("childControl", {})
                .get("device_id")
            )
            and (
                child_requests := [
                    cc["request_data"]
                    for req in requests
                    if (cc := req["params"].get("childControl"))
                ]
            )
        ):
            child_protocol = dev.protocol._transport.child_protocols[child_id]
            resp = await _get_child_responses(child_requests, child_protocol)
            resp = [{"result": {"response_data": resp}} for resp in resp]
            return {"multipleRequest": {"responses": resp}}

        if child_id:  # child single query
            child_protocol = dev.protocol._transport.child_protocols[child_id]
            resp_list = await _get_child_responses([requestData], child_protocol)
            resp = {"control_child": {"responseData": resp_list[0]}}
        else:
            resp = await dev.protocol._query(request, *args, **kwargs)

        return resp

    mocker.patch.object(new_dev.protocol, "query", side_effect=_query)

    first_update_time = time.monotonic()
    assert new_dev._last_update_time == first_update_time

    await new_dev.update()

    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            mod = cast(SmartModule, check_dev.modules[modname])
            assert mod._last_update_time == first_update_time

    for mod in new_dev.modules.values():
        mod.MINIMUM_UPDATE_INTERVAL_SECS = 5
    freezer.tick(180)

    now = time.monotonic()
    await new_dev.update()

    child_tick = max(
        module.MINIMUM_HUB_CHILD_UPDATE_INTERVAL_SECS
        for child in new_dev.children
        for module in child.modules.values()
    )

    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            if modname in {"Firmware"}:
                continue
            mod = cast(SmartModule, check_dev.modules[modname])
            expected_update_time = first_update_time if dev_id else now
            assert mod._last_update_time == expected_update_time

    freezer.tick(child_tick)

    now = time.monotonic()
    await new_dev.update()

    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            if modname in {"Firmware"}:
                continue
            mod = cast(SmartModule, check_dev.modules[modname])

            assert mod._last_update_time == now


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
@pytest.mark.xdist_group(name="caplog")
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
        freezer.tick(max(module.update_interval for module in dev._modules.values()))

    module_queries: dict[str, dict[str, dict]] = {}
    if TYPE_CHECKING:
        from ..fakeprotocol_smart import FakeSmartTransport

        assert isinstance(dev.protocol._transport, FakeSmartTransport)
    if dev.protocol._transport.child_protocols:
        for child in new_dev.children:
            for modname, module in child._modules.items():
                if (
                    not (q := module.query())
                    and modname not in {"DeviceModule", "Light"}
                    and not module.SYSINFO_LOOKUP_KEYS
                ):
                    q = {f"get_dummy_{modname}": {}}
                    mocker.patch.object(module, "query", return_value=q)
                if q:
                    queries = module_queries.setdefault(child.device_id, {})
                    queries[cast(str, modname)] = q

    module_queries[""] = {
        cast(str, modname): q
        for modname, module in dev._modules.items()
        if (q := module.query()) and modname not in critical_modules
    }

    raise_error = True

    async def _query(request, *args, **kwargs):
        pass
        # If this is a childmultipleRequest query return the error wrapped
        child_id = None
        if (
            (cc := request.get("control_child"))
            and (child_id := cc.get("device_id"))
            and (requestData := cc["requestData"])
            and requestData["method"] == "multipleRequest"
            and (child_requests := requestData["params"]["requests"])
        ):
            if raise_error:
                if not isinstance(error_type, SmartErrorCode):
                    raise TimeoutError()
                if len(child_requests) > 1:
                    raise TimeoutError()

            if raise_error:
                resp = {
                    "method": child_requests[0]["method"],
                    "error_code": error_type.value,
                }
            else:
                child_protocol = dev.protocol._transport.child_protocols[child_id]
                resp = await _get_child_responses(child_requests, child_protocol)
            return {"control_child": {"responseData": {"result": {"responses": resp}}}}

        if (
            not raise_error
            or "component_nego" in request
            # allow the initial child device query
            or (
                "get_child_device_component_list" in request
                and "get_child_device_list" in request
                and len(request) == 2
            )
        ):
            if child_id:  # child single query
                child_protocol = dev.protocol._transport.child_protocols[child_id]
                resp_list = await _get_child_responses([requestData], child_protocol)
                resp = {"control_child": {"responseData": resp_list[0]}}
            else:
                resp = await dev.protocol._query(request, *args, **kwargs)
            if raise_error:
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

    mocker.patch.object(new_dev.protocol, "query", side_effect=_query)

    await new_dev.update()

    msg = f"Error querying {new_dev.host} for modules"
    assert msg in caplog.text
    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            mod = cast(SmartModule, check_dev.modules[modname])
            if modname in {"DeviceModule"} or (
                hasattr(mod, "_state_in_sysinfo") and mod._state_in_sysinfo is True
            ):
                continue
            assert mod.disabled is False, f"{modname} disabled"
            assert mod.update_interval == mod.UPDATE_INTERVAL_AFTER_ERROR_SECS
            for mod_query in modqueries[modname]:
                if not first_update or mod_query not in first_update_queries:
                    msg = f"Error querying {new_dev.host} individually for module query '{mod_query}"
                    assert msg in caplog.text

    # Query again should not run for the modules
    caplog.clear()
    await new_dev.update()
    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            mod = cast(SmartModule, check_dev.modules[modname])
            assert mod.disabled is False, f"{modname} disabled"

    freezer.tick(SmartModule.UPDATE_INTERVAL_AFTER_ERROR_SECS)

    caplog.clear()

    if recover:
        raise_error = False

    await new_dev.update()
    msg = f"Error querying {new_dev.host} for modules"
    if not recover:
        assert msg in caplog.text

    for dev_id, modqueries in module_queries.items():
        check_dev = new_dev._children[dev_id] if dev_id else new_dev
        for modname in modqueries:
            mod = cast(SmartModule, check_dev.modules[modname])
            if modname in {"DeviceModule"} or (
                hasattr(mod, "_state_in_sysinfo") and mod._state_in_sysinfo is True
            ):
                continue
            if not recover:
                assert mod.disabled is True, f"{modname} not disabled"
                assert mod._error_count == 2
                assert mod._last_update_error
                for mod_query in modqueries[modname]:
                    if not first_update or mod_query not in first_update_queries:
                        msg = f"Error querying {new_dev.host} individually for module query '{mod_query}"
                        assert msg in caplog.text
                # Test one of the raise_if_update_error
                if mod.name == "Energy":
                    emod = cast(Energy, mod)
                    with pytest.raises(KasaException, match="Module update error"):
                        assert emod.status is not None
            else:
                assert mod.disabled is False
                assert mod._error_count == 0
                assert mod._last_update_error is None
                # Test one of the raise_if_update_error doesn't raise
                if mod.name == "Energy":
                    emod = cast(Energy, mod)
                    assert emod.status is not None


async def test_get_modules():
    """Test getting modules for child and parent modules."""
    dummy_device = await get_device_for_fixture_protocol(
        "KS240(US)_1.0_1.0.5.json", "SMART"
    )
    from kasa.smart.modules import Cloud

    # Modules on device
    module = dummy_device.modules.get("Cloud")
    assert module
    assert module.device == dummy_device
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
    assert module.device != dummy_device
    assert module.device.parent == dummy_device

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


@variable_temp_smart
async def test_smart_temp_range(dev: Device):
    light = dev.modules.get(Module.Light)
    assert light
    color_temp_feat = light.get_feature("color_temp")
    assert color_temp_feat
    assert color_temp_feat.range


@device_smart
async def test_initialize_modules_sysinfo_lookup_keys(
    dev: SmartDevice, mocker: MockerFixture
):
    """Test that matching modules using SYSINFO_LOOKUP_KEYS are initialized correctly."""

    class AvailableKey(SmartModule):
        SYSINFO_LOOKUP_KEYS = ["device_id"]

    class NonExistingKey(SmartModule):
        SYSINFO_LOOKUP_KEYS = ["this_does_not_exist"]

    # The __init_subclass__ hook in smartmodule checks the path,
    # so we have to manually add these for testing.
    mocker.patch.dict(
        "kasa.smart.smartmodule.SmartModule.REGISTERED_MODULES",
        {
            AvailableKey._module_name(): AvailableKey,
            NonExistingKey._module_name(): NonExistingKey,
        },
    )

    # We have an already initialized device, so we try to initialize the modules again
    await dev._initialize_modules()

    assert "AvailableKey" in dev.modules
    assert "NonExistingKey" not in dev.modules


@device_smart
async def test_initialize_modules_required_component(
    dev: SmartDevice, mocker: MockerFixture
):
    """Test that matching modules using REQUIRED_COMPONENT are initialized correctly."""

    class AvailableComponent(SmartModule):
        REQUIRED_COMPONENT = "device"

    class NonExistingComponent(SmartModule):
        REQUIRED_COMPONENT = "this_does_not_exist"

    # The __init_subclass__ hook in smartmodule checks the path,
    # so we have to manually add these for testing.
    mocker.patch.dict(
        "kasa.smart.smartmodule.SmartModule.REGISTERED_MODULES",
        {
            AvailableComponent._module_name(): AvailableComponent,
            NonExistingComponent._module_name(): NonExistingComponent,
        },
    )

    # We have an already initialized device, so we try to initialize the modules again
    await dev._initialize_modules()

    assert "AvailableComponent" in dev.modules
    assert "NonExistingComponent" not in dev.modules


async def test_smartmodule_query():
    """Test that a module that doesn't set QUERY_GETTER_NAME has empty query."""

    class DummyModule(SmartModule):
        pass

    dummy_device = await get_device_for_fixture_protocol(
        "KS240(US)_1.0_1.0.5.json", "SMART"
    )
    mod = DummyModule(dummy_device, "dummy")
    assert mod.query() == {}


@hub_all
@pytest.mark.xdist_group(name="caplog")
@pytest.mark.requires_dummy
async def test_dynamic_devices(dev: Device, caplog: pytest.LogCaptureFixture):
    """Test dynamic child devices."""
    if not dev.children:
        pytest.skip(f"Device {dev.model} does not have children.")

    transport = dev.protocol._transport
    assert isinstance(transport, FakeSmartCamTransport | FakeSmartTransport)

    lu = dev._last_update
    assert lu
    child_device_info = lu.get("getChildDeviceList", lu.get("get_child_device_list"))
    assert child_device_info

    child_device_components = lu.get(
        "getChildDeviceComponentList", lu.get("get_child_device_component_list")
    )
    assert child_device_components

    mock_child_device_info = copy.deepcopy(child_device_info)
    mock_child_device_components = copy.deepcopy(child_device_components)

    first_child = child_device_info["child_device_list"][0]
    first_child_device_id = first_child["device_id"]

    first_child_components = next(
        iter(
            [
                cc
                for cc in child_device_components["child_component_list"]
                if cc["device_id"] == first_child_device_id
            ]
        )
    )

    first_child_fake_transport = transport.child_protocols[first_child_device_id]

    # Test adding devices
    start_child_count = len(dev.children)
    added_ids = []
    for i in range(1, 3):
        new_child = copy.deepcopy(first_child)
        new_child_components = copy.deepcopy(first_child_components)

        mock_device_id = f"mock_child_device_id_{i}"

        transport.child_protocols[mock_device_id] = first_child_fake_transport
        new_child["device_id"] = mock_device_id
        new_child_components["device_id"] = mock_device_id

        added_ids.append(mock_device_id)
        mock_child_device_info["child_device_list"].append(new_child)
        mock_child_device_components["child_component_list"].append(
            new_child_components
        )

    def mock_get_child_device_queries(method, params):
        if method in {"getChildDeviceList", "get_child_device_list"}:
            result = mock_child_device_info
        if method in {"getChildDeviceComponentList", "get_child_device_component_list"}:
            result = mock_child_device_components
        return {"result": result, "error_code": 0}

    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    for added_id in added_ids:
        assert added_id in dev._children
    expected_new_length = start_child_count + len(added_ids)
    assert len(dev.children) == expected_new_length

    # Test removing devices
    mock_child_device_info["child_device_list"] = [
        info
        for info in mock_child_device_info["child_device_list"]
        if info["device_id"] != first_child_device_id
    ]
    mock_child_device_components["child_component_list"] = [
        cc
        for cc in mock_child_device_components["child_component_list"]
        if cc["device_id"] != first_child_device_id
    ]

    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    expected_new_length -= 1
    assert len(dev.children) == expected_new_length

    # Test no child devices

    mock_child_device_info["child_device_list"] = []
    mock_child_device_components["child_component_list"] = []
    mock_child_device_info["sum"] = 0
    mock_child_device_components["sum"] = 0

    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert len(dev.children) == 0

    # Logging tests are only for smartcam hubs as smart hubs do not test categories
    if not isinstance(dev, SmartCamDevice):
        return

    # setup
    mock_child = copy.deepcopy(first_child)
    mock_components = copy.deepcopy(first_child_components)

    mock_child_device_info["child_device_list"] = [mock_child]
    mock_child_device_components["child_component_list"] = [mock_components]
    mock_child_device_info["sum"] = 1
    mock_child_device_components["sum"] = 1

    # Test can't find matching components

    mock_child["device_id"] = "no_comps_1"
    mock_components["device_id"] = "no_comps_2"

    caplog.set_level("DEBUG")
    caplog.clear()
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Could not find child components for device" in caplog.text

    caplog.clear()

    # Test doesn't log multiple
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Could not find child components for device" not in caplog.text

    # Test invalid category

    mock_child["device_id"] = "invalid_cat"
    mock_components["device_id"] = "invalid_cat"
    mock_child["category"] = "foobar"

    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Child device type not supported" in caplog.text

    caplog.clear()

    # Test doesn't log multiple
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Child device type not supported" not in caplog.text

    # Test no category

    mock_child["device_id"] = "no_cat"
    mock_components["device_id"] = "no_cat"
    mock_child.pop("category")

    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Child device type not supported" in caplog.text

    # Test only log once

    caplog.clear()
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Child device type not supported" not in caplog.text

    # Test no device_id

    mock_child.pop("device_id")

    caplog.clear()
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Could not find child id for device" in caplog.text

    # Test only log once

    caplog.clear()
    with patch.object(
        transport, "get_child_device_queries", side_effect=mock_get_child_device_queries
    ):
        await dev.update()

    assert "Could not find child id for device" not in caplog.text


@hubs_smart
async def test_unpair(dev: SmartDevice, mocker: MockerFixture):
    """Verify that unpair calls childsetup module."""
    if not dev.children:
        pytest.skip("device has no children")

    child = dev.children[0]

    assert child.parent is not None
    assert Module.ChildSetup in dev.modules
    cs = dev.modules[Module.ChildSetup]

    unpair_call = mocker.spy(cs, "unpair")

    unpair_feat = child.features.get("unpair")
    assert unpair_feat
    await unpair_feat.set_value(None)

    unpair_call.assert_called_with(child.device_id)
