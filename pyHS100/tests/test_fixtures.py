import datetime

from unittest.mock import patch

import pytest

from pyHS100 import DeviceType, SmartStripException, SmartDeviceException
from .newfakes import (
    BULB_SCHEMA,
    PLUG_SCHEMA,
    FakeTransportProtocol,
    CURRENT_CONSUMPTION_SCHEMA,
    TZ_SCHEMA,
)
from .conftest import (
    turn_on,
    handle_turn_on,
    plug,
    strip,
    bulb,
    color_bulb,
    non_color_bulb,
    has_emeter,
    no_emeter,
    dimmable,
    non_dimmable,
    variable_temp,
    non_variable_temp,
)


@plug
def test_plug_sysinfo(dev):
    assert dev.sys_info is not None
    PLUG_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Plug or dev.device_type == DeviceType.Strip
    assert dev.is_plug or dev.is_strip


@bulb
def test_bulb_sysinfo(dev):
    assert dev.sys_info is not None
    BULB_SCHEMA(dev.sys_info)

    assert dev.model is not None

    assert dev.device_type == DeviceType.Bulb
    assert dev.is_bulb


def test_state_info(dev):
    assert isinstance(dev.state_information, dict)


def test_invalid_connection(dev):
    with patch.object(FakeTransportProtocol, "query", side_effect=SmartDeviceException):
        with pytest.raises(SmartDeviceException):
            dev.is_on


def test_query_helper(dev):
    with pytest.raises(SmartDeviceException):
        dev._query_helper("test", "testcmd", {})
    # TODO check for unwrapping?


def test_deprecated_state(dev):
    with pytest.deprecated_call():
        dev.state = "OFF"
        assert dev.state == "OFF"
        assert not dev.is_on

    with pytest.deprecated_call():
        dev.state = "ON"
        assert dev.state == "ON"
        assert dev.is_on

    with pytest.deprecated_call():
        with pytest.raises(ValueError):
            dev.state = "foo"

    with pytest.deprecated_call():
        with pytest.raises(ValueError):
            dev.state = 1234


def test_deprecated_alias(dev):
    with pytest.deprecated_call():
        dev.alias = "foo"


def test_deprecated_mac(dev):
    with pytest.deprecated_call():
        dev.mac = 123123123123


@plug
def test_deprecated_led(dev):
    with pytest.deprecated_call():
        dev.led = True


@turn_on
def test_state(dev, turn_on):
    handle_turn_on(dev, turn_on)
    orig_state = dev.is_on
    if orig_state:
        dev.turn_off()
        assert not dev.is_on
        assert dev.is_off
        dev.turn_on()
        assert dev.is_on
        assert not dev.is_off
    else:
        dev.turn_on()
        assert dev.is_on
        assert not dev.is_off
        dev.turn_off()
        assert not dev.is_on
        assert dev.is_off


@no_emeter
def test_no_emeter(dev):
    assert not dev.has_emeter

    with pytest.raises(SmartDeviceException):
        dev.get_emeter_realtime()
    with pytest.raises(SmartDeviceException):
        dev.get_emeter_daily()
    with pytest.raises(SmartDeviceException):
        dev.get_emeter_monthly()
    with pytest.raises(SmartDeviceException):
        dev.erase_emeter_stats()


@has_emeter
def test_get_emeter_realtime(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    current_emeter = dev.get_emeter_realtime()
    CURRENT_CONSUMPTION_SCHEMA(current_emeter)


@has_emeter
def test_get_emeter_daily(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert dev.get_emeter_daily(year=1900, month=1) == {}

    d = dev.get_emeter_daily()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = dev.get_emeter_daily(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
def test_get_emeter_monthly(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    assert dev.get_emeter_monthly(year=1900) == {}

    d = dev.get_emeter_monthly()
    assert len(d) > 0

    k, v = d.popitem()
    assert isinstance(k, int)
    assert isinstance(v, float)

    # Test kwh (energy, energy_wh)
    d = dev.get_emeter_monthly(kwh=False)
    k2, v2 = d.popitem()
    assert v * 1000 == v2


@has_emeter
def test_emeter_status(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    assert dev.has_emeter

    d = dev.get_emeter_realtime()

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
    assert dev.has_emeter

    dev.erase_emeter()


@has_emeter
def test_current_consumption(dev):
    if dev.is_strip:
        pytest.skip("Disabled for HS300 temporarily")

    if dev.has_emeter:
        x = dev.current_consumption()
        assert isinstance(x, float)
        assert x >= 0.0
    else:
        assert dev.current_consumption() is None


def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias
    assert isinstance(original, str)

    dev.set_alias(test_alias)
    assert dev.alias == test_alias

    dev.set_alias(original)
    assert dev.alias == original


@plug
def test_led(dev):
    original = dev.led

    dev.set_led(False)
    assert not dev.led
    dev.set_led(True)

    assert dev.led

    dev.set_led(original)


@plug
def test_on_since(dev):
    assert isinstance(dev.on_since, datetime.datetime)


def test_icon(dev):
    assert set(dev.icon.keys()), {"icon", "hash"}


def test_time(dev):
    assert isinstance(dev.time, datetime.datetime)
    # TODO check setting?


def test_timezone(dev):
    TZ_SCHEMA(dev.timezone)


def test_hw_info(dev):
    PLUG_SCHEMA(dev.hw_info)


def test_location(dev):
    PLUG_SCHEMA(dev.location)


def test_rssi(dev):
    PLUG_SCHEMA({"rssi": dev.rssi})  # wrapping for vol


def test_mac(dev):
    PLUG_SCHEMA({"mac": dev.mac})  # wrapping for val
    # TODO check setting?


@non_variable_temp
def test_temperature_on_nonsupporting(dev):
    assert dev.valid_temperature_range == (0, 0)

    # TODO test when device does not support temperature range
    with pytest.raises(SmartDeviceException):
        dev.set_color_temp(2700)
    with pytest.raises(SmartDeviceException):
        print(dev.color_temp)


@variable_temp
def test_out_of_range_temperature(dev):
    with pytest.raises(ValueError):
        dev.set_color_temp(1000)
    with pytest.raises(ValueError):
        dev.set_color_temp(10000)


@non_dimmable
def test_non_dimmable(dev):
    assert not dev.is_dimmable

    with pytest.raises(SmartDeviceException):
        assert dev.brightness == 0
    with pytest.raises(SmartDeviceException):
        dev.set_brightness(100)


@dimmable
@turn_on
def test_dimmable_brightness(dev, turn_on):
    handle_turn_on(dev, turn_on)
    assert dev.is_dimmable

    dev.set_brightness(50)
    assert dev.brightness == 50

    dev.set_brightness(10)
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        dev.set_brightness("foo")


@dimmable
def test_invalid_brightness(dev):
    assert dev.is_dimmable

    with pytest.raises(ValueError):
        dev.set_brightness(110)

    with pytest.raises(ValueError):
        dev.set_brightness(-100)


@color_bulb
@turn_on
def test_hsv(dev, turn_on):
    handle_turn_on(dev, turn_on)
    assert dev.is_color

    hue, saturation, brightness = dev.hsv
    assert 0 <= hue <= 255
    assert 0 <= saturation <= 100
    assert 0 <= brightness <= 100

    dev.set_hsv(hue=1, saturation=1, value=1)

    hue, saturation, brightness = dev.hsv
    assert hue == 1
    assert saturation == 1
    assert brightness == 1


@color_bulb
@turn_on
def test_invalid_hsv(dev, turn_on):
    handle_turn_on(dev, turn_on)

    assert dev.is_color

    for invalid_hue in [-1, 361, 0.5]:
        with pytest.raises(ValueError):
            dev.set_hsv(invalid_hue, 0, 0)

    for invalid_saturation in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            dev.set_hsv(0, invalid_saturation, 0)

    for invalid_brightness in [-1, 101, 0.5]:
        with pytest.raises(ValueError):
            dev.set_hsv(0, 0, invalid_brightness)


@non_color_bulb
def test_hsv_on_non_color(dev):
    assert not dev.is_color

    with pytest.raises(SmartDeviceException):
        dev.set_hsv(0, 0, 0)
    with pytest.raises(SmartDeviceException):
        print(dev.hsv)


@variable_temp
@turn_on
def test_try_set_colortemp(dev, turn_on):
    handle_turn_on(dev, turn_on)

    dev.set_color_temp(2700)
    assert dev.color_temp == 2700


@variable_temp
@turn_on
def test_deprecated_colortemp(dev, turn_on):
    handle_turn_on(dev, turn_on)
    with pytest.deprecated_call():
        dev.color_temp = 2700


@dimmable
def test_deprecated_brightness(dev):
    with pytest.deprecated_call():
        dev.brightness = 10


@non_variable_temp
def test_non_variable_temp(dev):
    with pytest.raises(SmartDeviceException):
        dev.set_color_temp(2700)


@color_bulb
@turn_on
def test_deprecated_hsv(dev, turn_on):
    handle_turn_on(dev, turn_on)
    with pytest.deprecated_call():
        dev.hsv = (1, 1, 1)


@strip
def test_children_is_on(dev):
    is_on = dev.get_is_on()
    for i in range(dev.num_children):
        assert is_on[i] == dev.get_is_on(index=i)


@strip
@turn_on
def test_children_change_state(dev, turn_on):
    handle_turn_on(dev, turn_on)
    for i in range(dev.num_children):
        orig_state = dev.get_is_on(index=i)
        if orig_state:
            dev.turn_off(index=i)
            assert not dev.get_is_on(index=i)
            assert dev.get_is_off(index=i)

            dev.turn_on(index=i)
            assert dev.get_is_on(index=i)
            assert not dev.get_is_off(index=i)
        else:
            dev.turn_on(index=i)
            assert dev.get_is_on(index=i)
            assert not dev.get_is_off(index=i)
            dev.turn_off(index=i)
            assert not dev.get_is_on(index=i)
            assert dev.get_is_off(index=i)


@strip
def test_children_bounds(dev):
    out_of_bounds = dev.num_children + 100

    with pytest.raises(SmartDeviceException):
        dev.turn_off(index=out_of_bounds)
    with pytest.raises(SmartDeviceException):
        dev.turn_on(index=out_of_bounds)
    with pytest.raises(SmartDeviceException):
        dev.get_is_on(index=out_of_bounds)
    with pytest.raises(SmartDeviceException):
        dev.get_alias(index=out_of_bounds)
    with pytest.raises(SmartDeviceException):
        dev.get_on_since(index=out_of_bounds)


@strip
def test_children_alias(dev):
    original = dev.get_alias()
    test_alias = "TEST1234"
    for idx in range(dev.num_children):
        dev.set_alias(alias=test_alias, index=idx)
        assert dev.get_alias(index=idx) == test_alias
        dev.set_alias(alias=original[idx], index=idx)
        assert dev.get_alias(index=idx) == original[idx]


@strip
def test_children_on_since(dev):
    for idx in range(dev.num_children):
        assert dev.get_on_since(index=idx)


@pytest.mark.skip("this test will wear out your relays")
def test_all_binary_states(dev):
    # test every binary state
    for state in range(2 ** dev.num_children):
        # create binary state map
        state_map = {}
        for plug_index in range(dev.num_children):
            state_map[plug_index] = bool((state >> plug_index) & 1)

            if state_map[plug_index]:
                dev.turn_on(index=plug_index)
            else:
                dev.turn_off(index=plug_index)

        # check state map applied
        for index, state in dev.get_is_on().items():
            assert state_map[index] == state

        # toggle each outlet with state map applied
        for plug_index in range(dev.num_children):

            # toggle state
            if state_map[plug_index]:
                dev.turn_off(index=plug_index)
            else:
                dev.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in dev.get_is_on().items():
                if index == plug_index:
                    assert state != state_map[index]
                else:
                    assert state == state_map[index]

            # reset state
            if state_map[plug_index]:
                dev.turn_on(index=plug_index)
            else:
                dev.turn_off(index=plug_index)

            # original state map should be restored
            for index, state in dev.get_is_on().items():
                assert state == state_map[index]


@strip
def test_children_get_emeter_realtime(dev):
    assert dev.has_emeter
    # test with index
    for plug_index in range(dev.num_children):
        emeter = dev.get_emeter_realtime(index=plug_index)
        CURRENT_CONSUMPTION_SCHEMA(emeter)

    # test without index
    for index, emeter in dev.get_emeter_realtime().items():
        CURRENT_CONSUMPTION_SCHEMA(emeter)

    # out of bounds
    with pytest.raises(SmartStripException):
        dev.get_emeter_realtime(index=dev.num_children + 100)


@strip
def test_children_get_emeter_daily(dev):
    assert dev.has_emeter
    # test with index
    for plug_index in range(dev.num_children):
        emeter = dev.get_emeter_daily(year=1900, month=1, index=plug_index)
        assert emeter == {}

        emeter = dev.get_emeter_daily(index=plug_index)
        assert len(emeter) > 0

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # test without index
    all_emeter = dev.get_emeter_daily(year=1900, month=1)
    for plug_index, emeter in all_emeter.items():
        assert emeter == {}

        emeter = dev.get_emeter_daily(index=plug_index)

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # out of bounds
    with pytest.raises(SmartStripException):
        dev.get_emeter_daily(year=1900, month=1, index=dev.num_children + 100)


@strip
def test_children_get_emeter_monthly(dev):
    assert dev.has_emeter
    # test with index
    for plug_index in range(dev.num_children):
        emeter = dev.get_emeter_monthly(year=1900, index=plug_index)
        assert emeter == {}

        emeter = dev.get_emeter_monthly()
        assert len(emeter) > 0

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # test without index
    all_emeter = dev.get_emeter_monthly(year=1900)
    for index, emeter in all_emeter.items():
        assert emeter == {}
        assert len(emeter) > 0

        k, v = emeter.popitem()
        assert isinstance(k, int)
        assert isinstance(v, float)

    # out of bounds
    with pytest.raises(SmartStripException):
        dev.get_emeter_monthly(year=1900, index=dev.num_children + 100)


def test_cache(dev):
    from datetime import timedelta

    dev.cache_ttl = timedelta(seconds=3)
    with patch.object(
        FakeTransportProtocol, "query", wraps=dev.protocol.query
    ) as query_mock:
        CHECK_COUNT = 1
        # Smartstrip calls sysinfo in its __init__ to request children, so
        # the even first get call here will get its results from the cache.
        if dev.is_strip:
            CHECK_COUNT = 0

        dev.get_sysinfo()
        assert query_mock.call_count == CHECK_COUNT
        dev.get_sysinfo()
        assert query_mock.call_count == CHECK_COUNT


def test_cache_invalidates(dev):
    from datetime import timedelta

    dev.cache_ttl = timedelta(seconds=0)

    with patch.object(
        FakeTransportProtocol, "query", wraps=dev.protocol.query
    ) as query_mock:
        dev.get_sysinfo()
        assert query_mock.call_count == 1
        dev.get_sysinfo()
        assert query_mock.call_count == 2
        # assert query_mock.called_once()
