import importlib
import inspect
import pkgutil
import re
import sys
from datetime import datetime
from unittest.mock import Mock, patch

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342
from voluptuous import (
    REMOVE_EXTRA,
    All,
    Any,
    Boolean,
    In,
    Invalid,
    Optional,
    Range,
    Schema,
)

import kasa
from kasa import Credentials, Device, DeviceConfig, SmartDeviceException
from kasa.iot import IotDevice
from kasa.smart import SmartChildDevice, SmartDevice

from .conftest import device_iot, handle_turn_on, has_emeter_iot, no_emeter_iot, turn_on
from .fakeprotocol_iot import FakeIotProtocol


def _get_subclasses(of_class):
    package = sys.modules["kasa"]
    subclasses = set()
    for _, modname, _ in pkgutil.iter_modules(package.__path__):
        importlib.import_module("." + modname, package="kasa")
        module = sys.modules["kasa." + modname]
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, of_class)
                and module.__package__ != "kasa"
            ):
                subclasses.add((module.__package__ + "." + name, obj))
    return subclasses


device_classes = pytest.mark.parametrize(
    "device_class_name_obj", _get_subclasses(Device), ids=lambda t: t[0]
)


@device_iot
async def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


@pytest.mark.requires_dummy
@device_iot
async def test_invalid_connection(dev):
    with patch.object(
        FakeIotProtocol, "query", side_effect=SmartDeviceException
    ), pytest.raises(SmartDeviceException):
        await dev.update()


@has_emeter_iot
async def test_initial_update_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    dev._legacy_features = set()
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    # Devices with small buffers may require 3 queries
    expected_queries = 2 if dev.max_device_response_size > 4096 else 3
    assert spy.call_count == expected_queries + len(dev.children)


@no_emeter_iot
async def test_initial_update_no_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    dev._legacy_features = set()
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    # 2 calls are necessary as some devices crash on unexpected modules
    # See #105, #120, #161
    assert spy.call_count == 2


@device_iot
async def test_query_helper(dev):
    with pytest.raises(SmartDeviceException):
        await dev._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


@device_iot
@turn_on
async def test_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    orig_state = dev.is_on
    if orig_state:
        await dev.turn_off()
        await dev.update()
        assert not dev.is_on
        assert dev.is_off

        await dev.turn_on()
        await dev.update()
        assert dev.is_on
        assert not dev.is_off
    else:
        await dev.turn_on()
        await dev.update()
        assert dev.is_on
        assert not dev.is_off

        await dev.turn_off()
        await dev.update()
        assert not dev.is_on
        assert dev.is_off


@device_iot
async def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    await dev.update()
    assert dev.alias == test_alias

    await dev.set_alias(original)
    await dev.update()
    assert dev.alias == original


@device_iot
@turn_on
async def test_on_since(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    orig_state = dev.is_on
    if "on_time" not in dev.sys_info and not dev.is_strip:
        assert dev.on_since is None
    elif orig_state:
        assert isinstance(dev.on_since, datetime)
    else:
        assert dev.on_since is None


@device_iot
async def test_time(dev):
    assert isinstance(await dev.get_time(), datetime)


@device_iot
async def test_timezone(dev):
    TZ_SCHEMA(await dev.get_timezone())


@device_iot
async def test_hw_info(dev):
    SYSINFO_SCHEMA(dev.hw_info)


@device_iot
async def test_location(dev):
    SYSINFO_SCHEMA(dev.location)


@device_iot
async def test_rssi(dev):
    SYSINFO_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


@device_iot
async def test_mac(dev):
    SYSINFO_SCHEMA({"mac": dev.mac})  # wrapping for val


@device_iot
async def test_representation(dev):
    import re

    pattern = re.compile("<.* model .* at .* (.*), is_on: .* - dev specific: .*>")
    assert pattern.match(str(dev))


@device_iot
async def test_childrens(dev):
    """Make sure that children property is exposed by every device."""
    if dev.is_strip:
        assert len(dev.children) > 0
    else:
        assert len(dev.children) == 0


@device_iot
async def test_children(dev):
    """Make sure that children property is exposed by every device."""
    if dev.is_strip:
        assert len(dev.children) > 0
        assert dev.has_children is True
    else:
        assert len(dev.children) == 0
        assert dev.has_children is False


@device_iot
async def test_internal_state(dev):
    """Make sure the internal state returns the last update results."""
    assert dev.internal_state == dev._last_update


@device_iot
async def test_features(dev):
    """Make sure features is always accessible."""
    sysinfo = dev._last_update["system"]["get_sysinfo"]
    if "feature" in sysinfo:
        assert dev._legacy_features == set(sysinfo["feature"].split(":"))
    else:
        assert dev._legacy_features == set()


@device_iot
async def test_max_device_response_size(dev):
    """Make sure every device return has a set max response size."""
    assert dev.max_device_response_size > 0


@device_iot
async def test_estimated_response_sizes(dev):
    """Make sure every module has an estimated response size set."""
    for mod in dev.modules.values():
        assert mod.estimated_query_response_size > 0


@device_classes
async def test_device_class_ctors(device_class_name_obj):
    """Make sure constructor api not broken for new and existing SmartDevices."""
    host = "127.0.0.2"
    port = 1234
    credentials = Credentials("foo", "bar")
    config = DeviceConfig(host, port_override=port, credentials=credentials)
    klass = device_class_name_obj[1]
    if issubclass(klass, SmartChildDevice):
        parent = SmartDevice(host, config=config)
        dev = klass(parent, 1)
    else:
        dev = klass(host, config=config)
    assert dev.host == host
    assert dev.port == port
    assert dev.credentials == credentials


@device_iot
async def test_modules_preserved(dev: IotDevice):
    """Make modules that are not being updated are preserved between updates."""
    dev._last_update["some_module_not_being_updated"] = "should_be_kept"
    await dev.update()
    assert dev._last_update["some_module_not_being_updated"] == "should_be_kept"


async def test_create_smart_device_with_timeout():
    """Make sure timeout is passed to the protocol."""
    host = "127.0.0.1"
    dev = IotDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100
    dev = SmartDevice(host, config=DeviceConfig(host, timeout=100))
    assert dev.protocol._transport._timeout == 100


async def test_create_thin_wrapper():
    """Make sure thin wrapper is created with the correct device type."""
    mock = Mock()
    config = DeviceConfig(
        host="test_host",
        port_override=1234,
        timeout=100,
        credentials=Credentials("username", "password"),
    )
    with patch("kasa.device_factory.connect", return_value=mock) as connect:
        dev = await Device.connect(config=config)
        assert dev is mock

    connect.assert_called_once_with(
        host=None,
        config=config,
    )


@device_iot
async def test_modules_not_supported(dev: IotDevice):
    """Test that unsupported modules do not break the device."""
    for module in dev.modules.values():
        assert module.is_supported is not None
    await dev.update()
    for module in dev.modules.values():
        assert module.is_supported is not None


@pytest.mark.parametrize(
    "device_class, use_class", kasa.deprecated_smart_devices.items()
)
def test_deprecated_devices(device_class, use_class):
    package_name = ".".join(use_class.__module__.split(".")[:-1])
    msg = f"{device_class} is deprecated, use {use_class.__name__} from package {package_name} instead"
    with pytest.deprecated_call(match=msg):
        getattr(kasa, device_class)
    packages = package_name.split(".")
    module = __import__(packages[0])
    for _ in packages[1:]:
        module = importlib.import_module(package_name, package=module.__name__)
    getattr(module, use_class.__name__)


def check_mac(x):
    if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", x.lower()):
        return x
    raise Invalid(x)


TZ_SCHEMA = Schema(
    {"zone_str": str, "dst_offset": int, "index": All(int, Range(min=0)), "tz_str": str}
)


SYSINFO_SCHEMA = Schema(
    {
        "active_mode": In(["schedule", "none", "count_down"]),
        "alias": str,
        "dev_name": str,
        "deviceId": str,
        "feature": str,
        "fwId": str,
        "hwId": str,
        "hw_ver": str,
        "icon_hash": str,
        "led_off": Boolean,
        "latitude": Any(All(float, Range(min=-90, max=90)), 0, None),
        "latitude_i": Any(
            All(int, Range(min=-900000, max=900000)),
            All(float, Range(min=-900000, max=900000)),
            0,
            None,
        ),
        "longitude": Any(All(float, Range(min=-180, max=180)), 0, None),
        "longitude_i": Any(
            All(int, Range(min=-18000000, max=18000000)),
            All(float, Range(min=-18000000, max=18000000)),
            0,
            None,
        ),
        "mac": check_mac,
        "model": str,
        "oemId": str,
        "on_time": int,
        "relay_state": int,
        "rssi": Any(int, None),  # rssi can also be positive, see #54
        "sw_ver": str,
        "type": str,
        "mic_type": str,
        "updating": Boolean,
        # these are available on hs220
        "brightness": int,
        "preferred_state": [
            {"brightness": All(int, Range(min=0, max=100)), "index": int}
        ],
        "next_action": {"type": int},
        "child_num": Optional(Any(None, int)),
        "children": Optional(list),
    },
    extra=REMOVE_EXTRA,
)
