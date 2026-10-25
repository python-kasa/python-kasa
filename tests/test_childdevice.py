import inspect
import logging
import time
from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory
from pytest_mock import MockerFixture

from kasa import Device, DeviceUnavailableError, Module
from kasa.device_type import DeviceType
from kasa.protocols.smartprotocol import SmartProtocol, _ChildProtocolWrapper
from kasa.smart.smartchilddevice import SmartChildDevice
from kasa.smart.smartdevice import NON_HUB_PARENT_ONLY_MODULES, SmartDevice

from .conftest import (
    parametrize,
    parametrize_combine,
    parametrize_subtract,
    strip_iot,
    strip_smart,
)
from .fakeprotocol_smart import FakeSmartTransport

has_children_smart = parametrize(
    "has children", component_filter="control_child", protocol_filter={"SMART"}
)
hub_smart = parametrize(
    "smart hub", device_type_filter=[DeviceType.Hub], protocol_filter={"SMART"}
)
non_hub_parent_smart = parametrize_subtract(has_children_smart, hub_smart)

has_children = parametrize_combine([has_children_smart, strip_iot])


@strip_smart
def test_childdevice_init(
    dev, dummy_protocol: SmartProtocol, mocker: MockerFixture
) -> None:
    """Test that child devices get initialized and use protocol wrapper."""
    assert len(dev.children) > 0

    first = dev.children[0]
    assert isinstance(first.protocol, _ChildProtocolWrapper)

    assert first._info["category"] == "plug.powerstrip.sub-plug"
    assert "position" in first._info


@strip_smart
async def test_childdevice_update(
    dev, dummy_protocol: SmartProtocol, mocker: MockerFixture
) -> None:
    """Test that parent update updates children."""
    child_info = dev.internal_state["get_child_device_list"]
    child_list = child_info["child_device_list"]

    assert len(dev.children) == child_info["sum"]
    first = dev.children[0]

    await dev.update()

    assert dev._info != first._info
    assert child_list[0] == first._info


@strip_smart
async def test_childdevice_properties(dev: SmartChildDevice):
    """Check that accessing childdevice properties do not raise exceptions."""
    assert len(dev.children) > 0

    first = dev.children[0]

    # children do not have children
    assert not first.children

    def _test_property_getters():
        """Try accessing all properties and return a list of encountered exceptions."""
        exceptions = []
        properties = inspect.getmembers(
            first.__class__, lambda o: isinstance(o, property)
        )
        for prop in properties:
            name, _ = prop
            # Skip emeter and time properties
            # TODO: needs API cleanup, emeter* should probably be removed in favor
            #  of access through features/modules, handling of time* needs decision.
            if (
                name.startswith("emeter_")
                or name.startswith("time")
                or name.startswith("fan")
                or name.startswith("color")
                or name.startswith("brightness")
                or name.startswith("valid_temperature_range")
                or name.startswith("hsv")
                or name.startswith("effect")
            ):
                continue
            try:
                _ = getattr(first, name)
            except Exception as ex:
                exceptions.append(ex)

        return exceptions

    exceptions = list(_test_property_getters())
    if exceptions:
        raise ExceptionGroup("Accessing child properties caused exceptions", exceptions)


@non_hub_parent_smart
async def test_parent_only_modules(
    dev, dummy_protocol: SmartProtocol, mocker: MockerFixture
) -> None:
    """Test that parent only modules are not available on children."""
    for child in dev.children:
        for module in NON_HUB_PARENT_ONLY_MODULES:
            assert module not in [type(module) for module in child.modules.values()]


@has_children
async def test_parent_property(dev: Device) -> None:
    """Test a child device exposes it's parent."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    assert dev.parent is None
    for child in dev.children:
        assert child.parent == dev


@hub_smart
@pytest.mark.requires_dummy
@pytest.mark.parametrize(
    ("status", "is_available"), [("online", True), ("offline", False)]
)
async def test_child_is_available(dev: Device, status: str, is_available: bool) -> None:
    """Test a hub child reports the reachability status from the hub."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    assert isinstance(dev.protocol._transport, FakeSmartTransport)
    child_list = dev.protocol._transport.info["get_child_device_list"]
    child_list["child_device_list"][0]["status"] = status

    await dev.update()

    child = dev.children[0]
    assert child.is_available is is_available
    assert child.features["available"].value is is_available
    assert dev.is_available is True


@hub_smart
@pytest.mark.requires_dummy
@pytest.mark.parametrize(
    "write",
    [
        pytest.param(lambda child: child.set_alias("new"), id="set_alias"),
        pytest.param(lambda child: child.reboot(), id="reboot"),
        pytest.param(
            lambda child: next(iter(child.modules.values())).call(
                "set_device_info", {"a": 1}
            ),
            id="module_call",
        ),
    ],
)
@pytest.mark.parametrize("removed", [False, True], ids=["offline", "removed"])
async def test_unavailable_child_refuses_writes(
    dev: Device, write, removed: bool, mocker: MockerFixture
) -> None:
    """Test writes to an unreachable hub child fail without contacting the hub."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    child = dev.children[0]
    assert isinstance(child, SmartChildDevice)
    assert isinstance(dev.protocol._transport, FakeSmartTransport)
    info = dev.protocol._transport.info
    child_list = info["get_child_device_list"]
    if removed:
        child_list["child_device_list"].pop(0)
        child_list["sum"] -= 1
        info["get_child_device_component_list"]["child_component_list"] = [
            c
            for c in info["get_child_device_component_list"]["child_component_list"]
            if c["device_id"] != child.device_id
        ]
    else:
        child_list["child_device_list"][0]["status"] = "offline"
    await dev.update()
    query = mocker.spy(dev.protocol, "query")

    assert child.is_available is False
    with pytest.raises(DeviceUnavailableError):
        await write(child)
    query.assert_not_called()

    await child._query_helper("get_device_info")
    query.assert_called_once()


@hub_smart
@pytest.mark.requires_dummy
@pytest.mark.xdist_group(name="caplog")
async def test_child_availability_change_logged_once(
    dev: Device, caplog: pytest.LogCaptureFixture
) -> None:
    """Test going offline and coming back are each logged once."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    assert isinstance(dev.protocol._transport, FakeSmartTransport)
    child_info = dev.protocol._transport.info["get_child_device_list"]
    child_id = child_info["child_device_list"][0]["device_id"]
    caplog.set_level(logging.DEBUG)

    child_info["child_device_list"][0]["status"] = "offline"
    await dev.update()
    await dev.update()
    assert caplog.text.count(f"({child_id}) available: False") == 1

    child_info["child_device_list"][0]["status"] = "online"
    await dev.update()
    await dev.update()
    assert caplog.text.count(f"({child_id}) available: True") == 1


@has_children_smart
@pytest.mark.requires_dummy
async def test_child_time(dev: Device, freezer: FrozenDateTimeFactory) -> None:
    """Test a child device gets the time from it's parent module.

    This is excluded from real device testing as the test often fail if the
    device time is not in the past.
    """
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    fallback_time = datetime.now(UTC).astimezone().replace(microsecond=0)
    assert dev.parent is None
    for child in dev.children:
        assert child.time != fallback_time


@pytest.mark.xdist_group(name="caplog")
async def test_child_device_type_unknown(caplog: pytest.LogCaptureFixture) -> None:
    """Test for device type when category is unknown."""

    class DummyDevice(SmartChildDevice):
        def __init__(self) -> None:
            super().__init__(
                SmartDevice("127.0.0.1"),
                {"device_id": "1", "category": "foobar"},
                {
                    "component_list": [{"id": "device", "ver_code": 1}],
                },
            )

    assert DummyDevice().device_type is DeviceType.Unknown
    msg = "Unknown child device type foobar for model None, please open issue"
    assert msg in caplog.text


@parametrize(
    "hub with cloud-connected sensor",
    model_filter={"H100(EU)_1.0_1.5.10", "KH100(UK)_1.0_1.5.6"},
    protocol_filter={"SMART"},
)
@pytest.mark.requires_dummy
async def test_child_partial_update_keeps_module_data(
    dev: SmartDevice, mocker: MockerFixture
) -> None:
    """Keep cached module data when only another child module is queried."""
    child = next(
        child
        for child in dev.children
        if Module.Cloud in child.modules and Module.TriggerLogs in child.modules
    )
    assert isinstance(child, SmartChildDevice)
    cached = child.modules[Module.TriggerLogs]
    cached_data = cached.data.copy()
    cached_logs = cached.logs
    for module in child.modules.values():
        module._last_update_time = time.monotonic()
    due = child.modules[Module.Cloud]
    due._last_update_time = None
    query = mocker.spy(child.protocol, "query")

    await child.update()

    query.assert_called_once_with(due.query())
    assert cached.data == cached_data
    assert cached.logs == cached_logs
    assert due.data
    assert cached._last_update_error is None
