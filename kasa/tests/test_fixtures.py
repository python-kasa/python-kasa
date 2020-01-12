import asyncio
import datetime
from unittest.mock import patch

import pytest

from kasa import DeviceType, SmartDeviceException, SmartStrip

from .conftest import (
    bulb,
    color_bulb,
    dimmable,
    handle_turn_on,
    has_emeter,
    no_emeter,
    non_color_bulb,
    non_dimmable,
    non_variable_temp,
    plug,
    strip,
    turn_on,
    variable_temp,
)
from .newfakes import (
    BULB_SCHEMA,
    CURRENT_CONSUMPTION_SCHEMA,
    PLUG_SCHEMA,
    TZ_SCHEMA,
    FakeTransportProtocol,
)


@pytest.mark.asyncio
@plug
async def test_plug_sysinfo(dev):
    assert dev.sys_info is not None
    PLUG_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip
    assert dev.is_plug or dev.is_strip


@pytest.mark.asyncio
@bulb
async def test_bulb_sysinfo(dev):
    assert dev.sys_info is not None
    BULB_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Bulb
    assert dev.is_bulb


@pytest.mark.asyncio
async def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


@pytest.mark.asyncio
async def test_invalid_connection(dev):
    with patch.object(FakeTransportProtocol, "query", side_effect=SmartDeviceException):
        with pytest.raises(SmartDeviceException):
            await dev.update()
            dev.is_on


@pytest.mark.asyncio
async def test_query_helper(dev):
    with pytest.raises(SmartDeviceException):
        await dev._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


@pytest.mark.asyncio
@turn_on
async def test_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    orig_state = dev.is_on
    if orig_state:
        await dev.turn_off()
        assert not dev.is_on
        assert dev.is_off

        await dev.turn_on()
        assert dev.is_on
        assert not dev.is_off
    else:
        await dev.turn_on()
        assert dev.is_on
        assert not dev.is_off

        await dev.turn_off()
        assert not dev.is_on
        assert dev.is_off


@pytest.mark.asyncio
@no_emeter
async def test_no_emeter(dev):
    assert not dev.has_emeter

    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_realtime()
    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_daily()
    with pytest.raises(SmartDeviceException):
        await dev.get_emeter_monthly()
    with pytest.raises(SmartDeviceException):
        await dev.erase_emeter_stats()


@pytest.mark.asyncio
@has_emeter
async def test_get_emeter_realtime(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    current_emeter = await dev.get_emeter_realtime()
    CURRENT_CONSUMPTION_SCHEMA(current_emeter)


@pytest.mark.asyncio
@has_emeter
async def test_get_emeter_daily(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert await dev.get_emeter_daily(year=1900, month=1) == {}

    d = await dev.get_emeter_daily()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await dev.get_emeter_daily(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@pytest.mark.asyncio
@has_emeter
async def test_get_emeter_monthly(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert await dev.get_emeter_monthly(year=1900) == {}

    d = await dev.get_emeter_monthly()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = await dev.get_emeter_monthly(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@pytest.mark.asyncio
@has_emeter
async def test_emeter_status(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    d = await dev.get_emeter_realtime()

    with pytest.raises(KeyError):
        assert d["foo"]

    assert d["power_mw"] == d["power"] * 1000
    # bulbs have only power according to tplink simulator.
    if not dev.is_bulb:
        assert d["voltage_mv"] == d["voltage"] * 1000

        assert d["current_ma"] == d["current"] * 1000
        assert d["total_wh"] == d["total"] * 1000


@pytest.mark.asyncio
@pytest.mark.skip("not clearing your stats..")
@has_emeter
async def test_erase_emeter_stats(dev):
    assert dev.has_emeter

    await dev.erase_emeter()


@pytest.mark.asyncio
@has_emeter
async def test_current_consumption(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    if dev.has_emeter:
        x = await dev.current_consumption()
        assert isinstance(x, float)
        assert x >= 0.0
    else:
        assert await dev.current_consumption() is None


@pytest.mark.asyncio
async def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    assert dev.alias == test_alias

    await dev.set_alias(original)
    assert dev.alias == original


@pytest.mark.asyncio
@plug
async def test_led(dev):
    original = dev.led

    await dev.set_led(False)
    assert not dev.led

    await dev.set_led(True)
    assert dev.led

    await dev.set_led(original)


@pytest.mark.asyncio
@plug
async def test_on_since(dev):
    assert isinstance(dev.on_since, datetime.datetime)


@pytest.mark.asyncio
async def test_icon(dev):
    assert set((await dev.get_icon()).keys()), {"icon", "hash"}


@pytest.mark.asyncio
async def test_time(dev):
    assert isinstance(await dev.get_time(), datetime.datetime)
    # TODO check setting?


@pytest.mark.asyncio
async def test_timezone(dev):
    TZ_SCHEMA(await dev.get_timezone())


@pytest.mark.asyncio
async def test_hw_info(dev):
    PLUG_SCHEMA(dev.hw_info)


@pytest.mark.asyncio
async def test_location(dev):
    PLUG_SCHEMA(dev.location)


@pytest.mark.asyncio
async def test_rssi(dev):
    PLUG_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


@pytest.mark.asyncio
async def test_mac(dev):
    PLUG_SCHEMA({"mac": dev.mac})  # wrapping for val
    # TODO check setting?


@pytest.mark.asyncio
@non_variable_temp
async def test_temperature_on_nonsupporting(dev):
    assert dev.valid_temperature_range == (0, 0)

    # TODO test when device does not support temperature range
    with pytest.raises(SmartDeviceException):
        await dev.set_color_temp(2700)
    with pytest.raises(SmartDeviceException):
        print(dev.color_temp)


@pytest.mark.asyncio
@variable_temp
async def test_out_of_range_temperature(dev):
    with pytest.raises(ValueError):
        await dev.set_color_temp(1000)
    with pytest.raises(ValueError):
        await dev.set_color_temp(10000)


@pytest.mark.asyncio
@non_dimmable
async def test_non_dimmable(dev):
    assert not dev.is_dimmable

    with pytest.raises(SmartDeviceException):
        assert dev.brightness == 0
    with pytest.raises(SmartDeviceException):
        await dev.set_brightness(100)


@pytest.mark.asyncio
@dimmable
@turn_on
async def test_dimmable_brightness(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_dimmable

    await dev.set_brightness(50)
    assert dev.brightness == 50

    await dev.set_brightness(10)
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        await dev.set_brightness("foo")


@pytest.mark.asyncio
@dimmable
async def test_invalid_brightness(dev):
    assert dev.is_dimmable

    with pytest.raises(ValueError):
        await dev.set_brightness(110)

    with pytest.raises(ValueError):
        await dev.set_brightness(-100)


@pytest.mark.asyncio
@color_bulb
@turn_on
async def test_hsv(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_color

    hue, saturation, brightness = dev.hsv
    assert 0 <= hue <= 255
    assert 0 <= saturation <= 100
    assert 0 <= brightness <= 100

    await dev.set_hsv(hue=1, saturation=1, value=1)

    hue, saturation, brightness = dev.hsv
    assert hue == 1
    assert saturation == 1
    assert brightness == 1


@pytest.mark.asyncio
@color_bulb
@turn_on
async def test_invalid_hsv(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    assert dev.is_color

    for invalid_hue in [-1, 361, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(invalid_hue, 0, 0)

    for invalid_saturation in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(0, invalid_saturation, 0)

    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            await dev.set_hsv(0, 0, invalid_brightness)


@pytest.mark.asyncio
@non_color_bulb
async def test_hsv_on_non_color(dev):
    assert not dev.is_color

    with pytest.raises(SmartDeviceException):
        await dev.set_hsv(0, 0, 0)
    with pytest.raises(SmartDeviceException):
        print(dev.hsv)


@pytest.mark.asyncio
@variable_temp
@turn_on
async def test_try_set_colortemp(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    await dev.set_color_temp(2700)
    assert dev.color_temp == 2700


@pytest.mark.asyncio
@non_variable_temp
async def test_non_variable_temp(dev):
    with pytest.raises(SmartDeviceException):
        await dev.set_color_temp(2700)


@pytest.mark.asyncio
@strip
@turn_on
async def test_children_change_state(dev, turn_on):
    await handle_turn_on(dev, turn_on)
    for plug in dev.plugs:
        orig_state = plug.is_on
        if orig_state:
            await plug.turn_off()
            assert not plug.is_on
            assert plug.is_off

            await plug.turn_on()
            assert plug.is_on
            assert not plug.is_off
        else:
            await plug.turn_on()
            assert plug.is_on
            assert not plug.is_off

            await plug.turn_off()
            assert not plug.is_on
            assert plug.is_off


@pytest.mark.asyncio
@strip
async def test_children_alias(dev):
    test_alias = "TEST1234"
    for plug in dev.plugs:
        original = plug.alias
        await plug.set_alias(alias=test_alias)
        assert plug.alias == test_alias

        await plug.set_alias(alias=original)
        assert plug.alias == original


@pytest.mark.asyncio
@strip
async def test_children_on_since(dev):
    for plug in dev.plugs:
        assert plug.on_since


@pytest.mark.asyncio
@pytest.mark.skip("this test will wear out your relays")
async def test_all_binary_states(dev):
    # test every binary state
    for state in range(2 ** dev.num_children):
        # create binary state map
        state_map = {}
        for plug_index in range(dev.num_children):
            state_map[plug_index] = bool((state >> plug_index) & 1)

            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

        # check state map applied
        for index, state in dev.is_on.items():
            assert state_map[index] == state

        # toggle each outlet with state map applied
        for plug_index in range(dev.num_children):

            # toggle state
            if state_map[plug_index]:
                await dev.turn_off(index=plug_index)
            else:
                await dev.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in dev.is_on.items():
                if index == plug_index:
                    assert state != state_map[index]
                else:
                    assert state == state_map[index]

            # reset state
            if state_map[plug_index]:
                await dev.turn_on(index=plug_index)
            else:
                await dev.turn_off(index=plug_index)

            # original state map should be restored
            for index, state in dev.is_on.items():
                assert state == state_map[index]


# def test_cache(dev):
#     from datetime import timedelta

#     dev.cache_ttl = timedelta(seconds=3)
#     with patch.object(
#         FakeTransportProtocol, "query", wraps=dev.protocol.query
#     ) as query_mock:
#         CHECK_COUNT = 1
#         # Smartstrip calls sysinfo in its __init__ to request children, so
#         # the even first get call here will get its results from the cache.
#         if dev.is_strip:
#             CHECK_COUNT = 0

#         dev.sys_info
#         assert query_mock.call_count == CHECK_COUNT
#         dev.sys_info
#         assert query_mock.call_count == CHECK_COUNT


# def test_cache_invalidates(dev):
#     from datetime import timedelta

#     dev.cache_ttl = timedelta(seconds=0)

#     with patch.object(
#         FakeTransportProtocol, "query", wraps=dev.protocol.query
#     ) as query_mock:
#         dev.sys_info
#         assert query_mock.call_count == 1
#         dev.sys_info
#         assert query_mock.call_count == 2
#         # assert query_mock.called_once()


def test_representation(dev):
    import re

    pattern = re.compile("<.* model .* at .* (.*), is_on: .* - dev specific: .*>")
    assert pattern.match(str(dev))
