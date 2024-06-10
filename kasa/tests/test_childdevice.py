import inspect
import sys

import pytest

from kasa.device_type import DeviceType
from kasa.smart.smartchilddevice import SmartChildDevice
from kasa.smart.smartdevice import NON_HUB_PARENT_ONLY_MODULES
from kasa.smartprotocol import _ChildProtocolWrapper

from .conftest import parametrize, parametrize_subtract, strip_smart

has_children_smart = parametrize(
    "has children", component_filter="control_child", protocol_filter={"SMART"}
)
hub_smart = parametrize(
    "smart hub", device_type_filter=[DeviceType.Hub], protocol_filter={"SMART"}
)
non_hub_parent_smart = parametrize_subtract(has_children_smart, hub_smart)


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
@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="exceptiongroup requires python3.11+",
)
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
