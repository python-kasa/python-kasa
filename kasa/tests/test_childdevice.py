import inspect
import sys

import pytest
from pytest_mock import MockerFixture

from kasa import Device
from kasa.device_type import DeviceType
from kasa.iot import IotDevice
from kasa.smart.smartchilddevice import SmartChildDevice
from kasa.smart.smartdevice import NON_HUB_PARENT_ONLY_MODULES
from kasa.smartprotocol import _ChildProtocolWrapper

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


@has_children
async def test_device_updates(dev: Device, mocker: MockerFixture):
    """Test usage of the update_children_or_parent parameter."""
    if not dev.children and dev.device_type is Device.Type.Hub:
        pytest.skip(f"Fixture for hub device {dev} does not have any children")
    assert dev.children
    parent_spy = mocker.spy(dev, "_update")
    child_spies = {child: mocker.spy(child, "_update") for child in dev.children}

    # update children, all devices call update
    await dev.update(update_children_or_parent=True)
    parent_spy.assert_called_once()
    for child_spy in child_spies.values():
        child_spy.assert_called_once()

    # do not update children, only parent calls update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    await dev.update(update_children_or_parent=False)
    parent_spy.assert_called_once()
    for child_spy in child_spies.values():
        child_spy.assert_not_called()

    # update parent, only the parent and one child call update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    child_to_update = dev.children[0]
    await child_to_update.update(update_children_or_parent=True)
    parent_spy.assert_called_once()
    assert child_to_update
    for child, child_spy in child_spies.items():
        if child == child_to_update:
            child_spy.assert_called_once()
        else:
            child_spy.assert_not_called()

    # do not update parent, only the one child calls update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    await child_to_update.update(update_children_or_parent=False)
    parent_spy.assert_not_called()
    assert child_to_update
    for child, child_spy in child_spies.items():
        if child == child_to_update:
            child_spy.assert_called_once()
        else:
            child_spy.assert_not_called()


@pytest.mark.parametrize("update_children_or_parent", [True, False])
@has_children
async def test_device_updates_deprecated(
    dev: Device, mocker: MockerFixture, update_children_or_parent
):
    """Test usage of the deprecated update_children parameter."""
    # update_children_or_parent parameter ensures the value is ignored

    if not dev.children and dev.device_type is Device.Type.Hub:
        pytest.skip(f"Fixture for hub device {dev} does not have any children")
    assert dev.children
    parent_spy = mocker.spy(dev, "_update")
    child_spies = {child: mocker.spy(child, "_update") for child in dev.children}

    msg = "update_children is deprecated, use update_children_or_parent"
    # update children, all devices call update
    with pytest.deprecated_call(match=msg):
        await dev.update(update_children_or_parent, update_children=True)

    parent_spy.assert_called_once()
    for child_spy in child_spies.values():
        child_spy.assert_called_once()

    # do not update children, only parent calls update for iot but for smart
    # all children update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    with pytest.deprecated_call(match=msg):
        await dev.update(update_children_or_parent, update_children=False)
    parent_spy.assert_called_once()
    for child_spy in child_spies.values():
        if isinstance(dev, IotDevice):
            child_spy.assert_not_called()
        else:
            child_spy.assert_called_once()

    # on child update_children true
    # only the child and no parent update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    child_to_update = dev.children[0]
    with pytest.deprecated_call(match=msg):
        await child_to_update.update(update_children_or_parent, update_children=True)
    parent_spy.assert_not_called()
    assert child_to_update
    for child, child_spy in child_spies.items():
        if child == child_to_update:
            child_spy.assert_called_once()
        else:
            child_spy.assert_not_called()

    # on child update_children false
    # only the child and no parent update
    parent_spy.reset_mock()
    for child_spy in child_spies.values():
        child_spy.reset_mock()

    with pytest.deprecated_call(match=msg):
        await child_to_update.update(update_children_or_parent, update_children=False)
    parent_spy.assert_not_called()
    assert child_to_update
    for child, child_spy in child_spies.items():
        if child == child_to_update:
            child_spy.assert_called_once()
        else:
            child_spy.assert_not_called()


@has_children
async def test_parent_property(dev: Device):
    """Test a child device exposes it's parent."""
    if not dev.children:
        pytest.skip(f"Device {dev} fixture does not have any children")

    assert dev.parent is None
    for child in dev.children:
        assert child.parent == dev
