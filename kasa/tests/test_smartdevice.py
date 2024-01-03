import inspect
from datetime import datetime
from unittest.mock import Mock, patch

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

import kasa
from kasa import Credentials, DeviceConfig, SmartDevice, SmartDeviceException

from .conftest import device_iot, handle_turn_on, has_emeter_iot, no_emeter_iot, turn_on
from .newfakes import PLUG_SCHEMA, TZ_SCHEMA, FakeTransportProtocol

# List of all SmartXXX classes including the SmartDevice base class
smart_device_classes = [
    dc
    for (mn, dc) in inspect.getmembers(
        kasa,
        lambda member: inspect.isclass(member)
        and (member == SmartDevice or issubclass(member, SmartDevice)),
    )
]


@device_iot
async def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


@pytest.mark.requires_dummy
@device_iot
async def test_invalid_connection(dev):
    with patch.object(
        FakeTransportProtocol, "query", side_effect=SmartDeviceException
    ), pytest.raises(SmartDeviceException):
        await dev.update()


@has_emeter_iot
async def test_initial_update_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    dev._features = set()
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    # Devices with small buffers may require 3 queries
    expected_queries = 2 if dev.max_device_response_size > 4096 else 3
    assert spy.call_count == expected_queries + len(dev.children)


@no_emeter_iot
async def test_initial_update_no_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    dev._features = set()
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
    PLUG_SCHEMA(dev.hw_info)


@device_iot
async def test_location(dev):
    PLUG_SCHEMA(dev.location)


@device_iot
async def test_rssi(dev):
    PLUG_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


@device_iot
async def test_mac(dev):
    PLUG_SCHEMA({"mac": dev.mac})  # wrapping for val


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
        assert dev.features == set(sysinfo["feature"].split(":"))
    else:
        assert dev.features == set()


@device_iot
async def test_max_device_response_size(dev):
    """Make sure every device return has a set max response size."""
    assert dev.max_device_response_size > 0


@device_iot
async def test_estimated_response_sizes(dev):
    """Make sure every module has an estimated response size set."""
    for mod in dev.modules.values():
        assert mod.estimated_query_response_size > 0


@pytest.mark.parametrize("device_class", smart_device_classes)
def test_device_class_ctors(device_class):
    """Make sure constructor api not broken for new and existing SmartDevices."""
    host = "127.0.0.2"
    port = 1234
    credentials = Credentials("foo", "bar")
    config = DeviceConfig(host, port_override=port, credentials=credentials)
    dev = device_class(host, config=config)
    assert dev.host == host
    assert dev.port == port
    assert dev.credentials == credentials


@device_iot
async def test_modules_preserved(dev: SmartDevice):
    """Make modules that are not being updated are preserved between updates."""
    dev._last_update["some_module_not_being_updated"] = "should_be_kept"
    await dev.update()
    assert dev._last_update["some_module_not_being_updated"] == "should_be_kept"


async def test_create_smart_device_with_timeout():
    """Make sure timeout is passed to the protocol."""
    host = "127.0.0.1"
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
        dev = await SmartDevice.connect(config=config)
        assert dev is mock

    connect.assert_called_once_with(
        host=None,
        config=config,
    )


@device_iot
async def test_modules_not_supported(dev: SmartDevice):
    """Test that unsupported modules do not break the device."""
    for module in dev.modules.values():
        assert module.is_supported is not None
    await dev.update()
    for module in dev.modules.values():
        assert module.is_supported is not None
