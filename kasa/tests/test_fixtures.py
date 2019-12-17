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


@plug
def test_plug_sysinfo(dev):
    dev.sync.update()
    assert dev.sys_info is not None
    PLUG_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip
    assert dev.is_plug or dev.is_strip


@bulb
def test_bulb_sysinfo(dev):
    dev.sync.update()
    assert dev.sys_info is not None
    BULB_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Bulb
    assert dev.is_bulb


def test_state_info(dev):
    dev.sync.update()
    assert isinstance(dev.sync.state_information, dict)


def test_invalid_connection(dev):
    with patch.object(FakeTransportProtocol, "query", side_effect=SmartDeviceException):
        with pytest.raises(SmartDeviceException):
            dev.sync.update()
            dev.is_on


def test_query_helper(dev):
    with pytest.raises(SmartDeviceException):
        dev.sync._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


@turn_on
def test_state(dev, turn_on):
    handle_turn_on(dev, turn_on)
    dev.sync.update()
    orig_state = dev.is_on
    if orig_state:
        dev.sync.turn_off()
        assert not dev.is_on
        assert dev.is_off
        dev.sync.turn_on()
        assert dev.is_on
        assert not dev.is_off
    else:
        dev.sync.turn_on()
        assert dev.is_on
        assert not dev.is_off
        dev.sync.turn_off()
        assert not dev.is_on
        assert dev.is_off


@no_emeter
def test_no_emeter(dev):
    dev.sync.update()
    assert not dev.has_emeter

    with pytest.raises(SmartDeviceException):
        dev.sync.get_emeter_realtime()
    with pytest.raises(SmartDeviceException):
        dev.sync.get_emeter_daily()
    with pytest.raises(SmartDeviceException):
        dev.sync.get_emeter_monthly()
    with pytest.raises(SmartDeviceException):
        dev.sync.erase_emeter_stats()


@has_emeter
def test_get_emeter_realtime(dev):
    dev.sync.update()
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    current_emeter = dev.sync.get_emeter_realtime()
    CURRENT_CONSUMPTION_SCHEMA(current_emeter)


@has_emeter
def test_get_emeter_daily(dev):
    dev.sync.update()
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert dev.sync.get_emeter_daily(year=1900, month=1) == {}

    d = dev.sync.get_emeter_daily()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = dev.sync.get_emeter_daily(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
def test_get_emeter_monthly(dev):
    dev.sync.update()
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert dev.sync.get_emeter_monthly(year=1900) == {}

    d = dev.sync.get_emeter_monthly()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = dev.sync.get_emeter_monthly(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
def test_emeter_status(dev):
    dev.sync.update()
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    d = dev.sync.get_emeter_realtime()

    with pytest.raises(KeyError):
        assert d["foo"]

    assert d["power_mw"] == d["power"] * 1000
    # bulbs have only power according to tplink simulator.
    if not dev.is_bulb:
        assert d["voltage_mv"] == d["voltage"] * 1000

        assert d["current_ma"] == d["current"] * 1000
        assert d["total_wh"] == d["total"] * 1000


@pytest.mark.skip("not clearing your stats..")
@has_emeter
def test_erase_emeter_stats(dev):
    dev.sync.update()
    assert dev.has_emeter

    dev.sync.erase_emeter()


@has_emeter
def test_current_consumption(dev):
    dev.sync.update()
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    if dev.has_emeter:
        x = dev.sync.current_consumption()
        assert isinstance(x, float)
        assert x >= 0.0
    else:
        assert dev.sync.current_consumption() is None


def test_alias(dev):
    dev.sync.update()
    test_alias = "TEST1234"
    original = dev.sync.alias

    assert isinstance(original, str)
    dev.sync.set_alias(test_alias)
    assert dev.sync.alias == test_alias

    dev.sync.set_alias(original)
    assert dev.sync.alias == original


@plug
def test_led(dev):
    dev.sync.update()
    original = dev.led

    dev.sync.set_led(False)
    assert not dev.led

    dev.sync.set_led(True)
    assert dev.led

    dev.sync.set_led(original)


@plug
def test_on_since(dev):
    dev.sync.update()
    assert isinstance(dev.on_since, datetime.datetime)


def test_icon(dev):
    assert set(dev.sync.get_icon().keys()), {"icon", "hash"}


def test_time(dev):
    assert isinstance(dev.sync.get_time(), datetime.datetime)
    # TODO check setting?


def test_timezone(dev):
    TZ_SCHEMA(dev.sync.get_timezone())


def test_hw_info(dev):
    dev.sync.update()
    PLUG_SCHEMA(dev.hw_info)


def test_location(dev):
    dev.sync.update()
    PLUG_SCHEMA(dev.location)


def test_rssi(dev):
    dev.sync.update()
    PLUG_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


def test_mac(dev):
    dev.sync.update()
    PLUG_SCHEMA({"mac": dev.mac})  # wrapping for val
    # TODO check setting?


@non_variable_temp
def test_temperature_on_nonsupporting(dev):
    dev.sync.update()
    assert dev.valid_temperature_range == (0, 0)

    # TODO test when device does not support temperature range
    with pytest.raises(SmartDeviceException):
        dev.sync.set_color_temp(2700)
    with pytest.raises(SmartDeviceException):
        print(dev.sync.color_temp)


@variable_temp
def test_out_of_range_temperature(dev):
    dev.sync.update()
    with pytest.raises(ValueError):
        dev.sync.set_color_temp(1000)
    with pytest.raises(ValueError):
        dev.sync.set_color_temp(10000)


@non_dimmable
def test_non_dimmable(dev):
    dev.sync.update()
    assert not dev.is_dimmable

    with pytest.raises(SmartDeviceException):
        assert dev.brightness == 0
    with pytest.raises(SmartDeviceException):
        dev.sync.set_brightness(100)


@dimmable
@turn_on
def test_dimmable_brightness(dev, turn_on):
    handle_turn_on(dev, turn_on)
    dev.sync.update()
    assert dev.is_dimmable

    dev.sync.set_brightness(50)
    assert dev.brightness == 50

    dev.sync.set_brightness(10)
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        dev.sync.set_brightness("foo")


@dimmable
def test_invalid_brightness(dev):
    dev.sync.update()
    assert dev.is_dimmable

    with pytest.raises(ValueError):
        dev.sync.set_brightness(110)

    with pytest.raises(ValueError):
        dev.sync.set_brightness(-100)


@color_bulb
@turn_on
def test_hsv(dev, turn_on):
    handle_turn_on(dev, turn_on)
    dev.sync.update()
    assert dev.is_color

    hue, saturation, brightness = dev.hsv
    assert 0 <= hue <= 255
    assert 0 <= saturation <= 100
    assert 0 <= brightness <= 100

    dev.sync.set_hsv(hue=1, saturation=1, value=1)

    hue, saturation, brightness = dev.hsv
    assert hue == 1
    assert saturation == 1
    assert brightness == 1


@color_bulb
@turn_on
def test_invalid_hsv(dev, turn_on):
    handle_turn_on(dev, turn_on)
    dev.sync.update()
    assert dev.is_color

    for invalid_hue in [-1, 361, 0.5]:
        with pytest.raises(ValueError):
            dev.sync.set_hsv(invalid_hue, 0, 0)

    for invalid_saturation in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            dev.sync.set_hsv(0, invalid_saturation, 0)

    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            dev.sync.set_hsv(0, 0, invalid_brightness)


@non_color_bulb
def test_hsv_on_non_color(dev):
    dev.sync.update()
    assert not dev.is_color

    with pytest.raises(SmartDeviceException):
        dev.sync.set_hsv(0, 0, 0)
    with pytest.raises(SmartDeviceException):
        print(dev.hsv)


@variable_temp
@turn_on
def test_try_set_colortemp(dev, turn_on):
    dev.sync.update()
    handle_turn_on(dev, turn_on)
    dev.sync.set_color_temp(2700)
    assert dev.sync.color_temp == 2700


@non_variable_temp
def test_non_variable_temp(dev):
    with pytest.raises(SmartDeviceException):
        dev.sync.update()
        dev.sync.set_color_temp(2700)


@strip
@turn_on
def test_children_change_state(dev, turn_on):
    dev.sync.update()
    handle_turn_on(dev, turn_on)
    for plug in dev.plugs:
        plug.sync.update()
        orig_state = plug.is_on
        if orig_state:
            plug.turn_off()
            plug.sync.update()
            assert not plug.is_on
            assert plug.is_off

            plug.sync.turn_on()
            plug.sync.update()
            assert plug.is_on
            assert not plug.is_off
        else:
            plug.sync.turn_on()
            plug.sync.update()
            assert plug.is_on
            assert not plug.is_off
            plug.sync.turn_off()
            plug.sync.update()
            assert not plug.is_on
            assert plug.is_off


@strip
def test_children_alias(dev):
    test_alias = "TEST1234"
    for plug in dev.plugs:
        plug.sync.update()
        original = plug.alias
        plug.sync.set_alias(alias=test_alias)
        plug.sync.update()
        assert plug.alias == test_alias
        plug.sync.set_alias(alias=original)
        plug.sync.update()
        assert plug.alias == original


@strip
def test_children_on_since(dev):
    for plug in dev.plugs:
        plug.sync.update()
        assert plug.on_since


@pytest.mark.skip("this test will wear out your relays")
def test_all_binary_states(dev):
    # test every binary state
    for state in range(2 ** dev.num_children):
        # create binary state map
        state_map = {}
        for plug_index in range(dev.num_children):
            state_map[plug_index] = bool((state >> plug_index) & 1)

            if state_map[plug_index]:
                dev.sync.turn_on(index=plug_index)
            else:
                dev.sync.turn_off(index=plug_index)

        # check state map applied
        for index, state in dev.is_on.items():
            assert state_map[index] == state

        # toggle each outlet with state map applied
        for plug_index in range(dev.num_children):

            # toggle state
            if state_map[plug_index]:
                dev.sync.turn_off(index=plug_index)
            else:
                dev.sync.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in dev.is_on.items():
                if index == plug_index:
                    assert state != state_map[index]
                else:
                    assert state == state_map[index]

            # reset state
            if state_map[plug_index]:
                dev.sync.turn_on(index=plug_index)
            else:
                dev.sync.turn_off(index=plug_index)

            # original state map should be restored
            for index, state in dev.is_on.items():
                assert state == state_map[index]


@strip
def test_children_get_emeter_realtime(dev):
    dev.sync.update()
    assert dev.has_emeter
    # test with index
    for plug in dev.plugs:
        plug.sync.update()
        emeter = plug.sync.get_emeter_realtime()
        CURRENT_CONSUMPTION_SCHEMA(emeter)

    # test without index
    # TODO test that sum matches the sum of individiaul plugs.

    # for index, emeter in dev.sync.get_emeter_realtime().items():
    #    CURRENT_CONSUMPTION_SCHEMA(emeter)


@strip
def test_children_get_emeter_daily(dev):
    dev.sync.update()
    assert dev.has_emeter
    # test individual emeters
    for plug in dev.plugs:
        plug.sync.update()
        emeter = plug.sync.get_emeter_daily(year=1900, month=1)
        assert emeter == {}

        emeter = plug.sync.get_emeter_daily()
        assert len(emeter) > 0

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # test sum of emeters
    all_emeter = dev.sync.get_emeter_daily(year=1900, month=1)

    k, v = all_emeter.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)


@strip
def test_children_get_emeter_monthly(dev):
    dev.sync.update()
    assert dev.has_emeter
    # test individual emeters
    for plug in dev.plugs:
        plug.sync.update()
        emeter = plug.sync.get_emeter_monthly(year=1900)
        assert emeter == {}

        emeter = plug.sync.get_emeter_monthly()
        assert len(emeter) > 0

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # test sum of emeters
    all_emeter = dev.sync.get_emeter_monthly(year=1900)

    k, v = all_emeter.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)


# def test_cache(dev):
#     from datetime import timedelta

#     dev.sync.cache_ttl = timedelta(seconds=3)
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

#     dev.sync.cache_ttl = timedelta(seconds=0)

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
