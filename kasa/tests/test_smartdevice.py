from datetime import datetime
from unittest.mock import patch

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import SmartDeviceException
from kasa.smartstrip import SmartStripPlug

from .conftest import handle_turn_on, has_emeter, no_emeter, pytestmark, turn_on
from .newfakes import PLUG_SCHEMA, TZ_SCHEMA, FakeTransportProtocol


async def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


@pytest.mark.requires_dummy
async def test_invalid_connection(dev):
    with patch.object(FakeTransportProtocol, "query", side_effect=SmartDeviceException):
        with pytest.raises(SmartDeviceException):
            await dev.update()


@has_emeter
async def test_initial_update_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    assert spy.call_count == 2 + len(dev.children)


@no_emeter
async def test_initial_update_no_emeter(dev, mocker):
    """Test that the initial update performs second query if emeter is available."""
    dev._last_update = None
    spy = mocker.spy(dev.protocol, "query")
    await dev.update()
    assert spy.call_count == 1


async def test_query_helper(dev):
    with pytest.raises(SmartDeviceException):
        await dev._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


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


async def test_time(dev):
    assert isinstance(await dev.get_time(), datetime)


async def test_timezone(dev):
    TZ_SCHEMA(await dev.get_timezone())


async def test_hw_info(dev):
    PLUG_SCHEMA(dev.hw_info)


async def test_location(dev):
    PLUG_SCHEMA(dev.location)


async def test_rssi(dev):
    PLUG_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


async def test_mac(dev):
    PLUG_SCHEMA({"mac": dev.mac})  # wrapping for val


async def test_representation(dev):
    import re

    pattern = re.compile("<.* model .* at .* (.*), is_on: .* - dev specific: .*>")
    assert pattern.match(str(dev))


async def test_childrens(dev):
    """Make sure that children property is exposed by every device."""
    if dev.is_strip:
        assert len(dev.children) > 0
    else:
        assert len(dev.children) == 0


async def test_internal_state(dev):
    """Make sure the internal state returns the last update results."""
    assert dev.internal_state == dev._last_update


async def test_features(dev):
    """Make sure features is always accessible."""
    sysinfo = dev._last_update["system"]["get_sysinfo"]
    if "feature" in sysinfo:
        assert dev.features == set(sysinfo["feature"].split(":"))
    else:
        assert dev.features == set()
