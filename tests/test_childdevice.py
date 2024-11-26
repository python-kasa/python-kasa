import inspect
from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Device
from kasa.device_type import DeviceType
from kasa.protocols.smartprotocol import _ChildProtocolWrapper
from kasa.smart.smartchilddevice import SmartChildDevice
from kasa.smart.smartdevice import NON_HUB_PARENT_ONLY_MODULES, SmartDevice

from .conftest import (
    parametrize,
    parametrize_combine,
    parametrize_subtract,
    strip_iot,
    strip_smart,
)

has_children_smart = parametrize(
    "has children", component_filter="control_child", protocol_filter={"SMART"}
)
hub_smart = parametrize(
    "smart hub", device_type_filter=[DeviceType.Hub], protocol_filter={"SMART"}
)
non_hub_parent_smart = parametrize_subtract(has_children_smart, hub_smart)

has_children = parametrize_combine([has_children_smart, strip_iot])


@strip_smart
def test_childdevice_init(dev, dummy_protocol, mocker):
    """Test that child devices get initialized and use protocol wrapper."""
    assert len(dev.children) > 0

    first = dev.children[0]
    assert isinstance(first.protocol, _ChildProtocolWrapper)

    assert first._info["category"] == "plug.powerstrip.sub-plug"
    assert "position" in first._info


@strip_smart
async def test_childdevice_update(dev, dummy_protocol, mocker):
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
async def test_parent_only_modules(dev, dummy_protocol, mocker):
    """Test that parent only modules are not available on children."""
    for child in dev.children:
        for module in NON_HUB_PARENT_ONLY_MODULES:
            assert module not in [type(module) for module in child.modules.values()]


@has_children
async def test_parent_property(dev: Device):
    """Test a child device exposes it's parent."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    assert dev.parent is None
    for child in dev.children:
        assert child.parent == dev


@has_children_smart
@pytest.mark.requires_dummy
async def test_child_time(dev: Device, freezer: FrozenDateTimeFactory):
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
async def test_child_device_type_unknown(caplog):
    """Test for device type when category is unknown."""

    class DummyDevice(SmartChildDevice):
        def __init__(self):
            super().__init__(
                SmartDevice("127.0.0.1"),
                {"device_id": "1", "category": "foobar"},
                {"device", 1},
            )

    assert DummyDevice().device_type is DeviceType.Unknown
    msg = "Unknown child device type foobar for model None, please open issue"
    assert msg in caplog.text
