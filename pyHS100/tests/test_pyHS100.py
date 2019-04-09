from unittest import TestCase, skip
from voluptuous import Schema, Invalid, All, Any, Range, Coerce
from functools import partial
import datetime
import re
from typing import Dict  # noqa: F401

from .. import SmartPlug, SmartDeviceException
from .fakes import (FakeTransportProtocol,
                    sysinfo_hs100,
                    sysinfo_hs105,
                    sysinfo_hs110,
                    sysinfo_hs110_au_v2,
                    sysinfo_hs200,
                    sysinfo_hs220,
                    )

# Set IP instead of None if you want to run tests on a device.
PLUG_IP = None


def check_int_bool(x):
    if x != 0 and x != 1:
        raise Invalid(x)
    return x


def check_mac(x):
    if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", x.lower()):
        return x
    raise Invalid(x)


def check_mode(x):
    if x in ['schedule', 'none']:
        return x

    raise Invalid("invalid mode {}".format(x))


class TestSmartPlugHS100(TestCase):
    SYSINFO = sysinfo_hs100  # type: Dict
    # these schemas should go to the mainlib as
    # they can be useful when adding support for new features/devices
    # as well as to check that faked devices are operating properly.
    sysinfo_schema = Schema({
        'active_mode': check_mode,
        'alias': str,
        'dev_name': str,
        'deviceId': str,
        'feature': str,
        'fwId': str,
        'hwId': str,
        'hw_ver': str,
        'icon_hash': str,
        'led_off': check_int_bool,
        'latitude': Any(All(float, Range(min=-90, max=90)), None),
        'latitude_i': Any(All(float, Range(min=-90, max=90)), None),
        'longitude': Any(All(float, Range(min=-180, max=180)), None),
        'longitude_i': Any(All(float, Range(min=-180, max=180)), None),
        'mac': check_mac,
        'model': str,
        'oemId': str,
        'on_time': int,
        'relay_state': int,
        'rssi': Any(int, None),  # rssi can also be positive, see #54
        'sw_ver': str,
        'type': str,
        'mic_type': str,
        'updating': check_int_bool,
        # these are available on hs220
        'brightness': int,
        'preferred_state': [{
            'brightness': All(int, Range(min=0, max=100)),
            'index': int,
        }],
        "next_action": {"type": int},

    })

    current_consumption_schema = Schema(Any({
        'voltage': Any(All(float, Range(min=0, max=300)), None),
        'power': Any(Coerce(float, Range(min=0)), None),
        'total': Any(Coerce(float, Range(min=0)), None),
        'current': Any(All(float, Range(min=0)), None),

        'voltage_mv': Any(All(float, Range(min=0, max=300000)), None),
        'power_mw': Any(Coerce(float, Range(min=0)), None),
        'total_wh': Any(Coerce(float, Range(min=0)), None),
        'current_ma': Any(All(float, Range(min=0)), None),
    }, None))

    tz_schema = Schema({
        'zone_str': str,
        'dst_offset': int,
        'index': All(int, Range(min=0)),
        'tz_str': str,
    })

    def setUp(self):
        if PLUG_IP is not None:
            self.plug = SmartPlug(PLUG_IP)
        else:
            self.plug = SmartPlug("127.0.0.1",
                                  protocol=FakeTransportProtocol(self.SYSINFO))

    def tearDown(self):
        self.plug = None

    def test_initialize(self):
        self.assertIsNotNone(self.plug.sys_info)
        self.sysinfo_schema(self.plug.sys_info)

    def test_initialize_invalid_connection(self):
        plug = SmartPlug('127.0.0.1',
                         protocol=FakeTransportProtocol(self.SYSINFO,
                                                        invalid=True))
        with self.assertRaises(SmartDeviceException):
            plug.sys_info['model']

    def test_query_helper(self):
        with self.assertRaises(SmartDeviceException):
            self.plug._query_helper("test", "testcmd", {})
        # TODO check for unwrapping?

    def test_state(self):
        def set_invalid(x):
            self.plug.state = x

        set_invalid_int = partial(set_invalid, 1234)
        self.assertRaises(ValueError, set_invalid_int)

        set_invalid_str = partial(set_invalid, "1234")
        self.assertRaises(ValueError, set_invalid_str)

        set_invalid_bool = partial(set_invalid, True)
        self.assertRaises(ValueError, set_invalid_bool)

        orig_state = self.plug.state
        if orig_state == SmartPlug.SWITCH_STATE_OFF:
            self.plug.state = "ON"
            self.assertTrue(self.plug.state == SmartPlug.SWITCH_STATE_ON)
            self.plug.state = "OFF"
            self.assertTrue(self.plug.state == SmartPlug.SWITCH_STATE_OFF)
        elif orig_state == SmartPlug.SWITCH_STATE_ON:
            self.plug.state = "OFF"
            self.assertTrue(self.plug.state == SmartPlug.SWITCH_STATE_OFF)
            self.plug.state = "ON"
            self.assertTrue(self.plug.state == SmartPlug.SWITCH_STATE_ON)
        elif orig_state == SmartPlug.SWITCH_STATE_UNKNOWN:
            self.fail("can't test for unknown state")

    def test_get_sysinfo(self):
        # initialize checks for this already, but just to be sure
        self.sysinfo_schema(self.plug.get_sysinfo())

    def test_turns_and_isses(self):
        orig_state = self.plug.is_on

        if orig_state:
            self.plug.turn_off()
            self.assertFalse(self.plug.is_on)
            self.assertTrue(self.plug.is_off)
            self.plug.turn_on()
            self.assertTrue(self.plug.is_on)
        else:
            self.plug.turn_on()
            self.assertFalse(self.plug.is_off)
            self.assertTrue(self.plug.is_on)
            self.plug.turn_off()
            self.assertTrue(self.plug.is_off)

    def test_has_emeter(self):
        # a not so nice way for checking for emeter availability..
        if "110" in self.plug.sys_info["model"]:
            self.assertTrue(self.plug.has_emeter)
        else:
            self.assertFalse(self.plug.has_emeter)

    def test_get_emeter_realtime(self):
        if self.plug.has_emeter:
            current_emeter = self.plug.get_emeter_realtime()
            self.current_consumption_schema(current_emeter)
        else:
            self.assertEqual(self.plug.get_emeter_realtime(), None)

    def test_get_emeter_daily(self):
        if self.plug.has_emeter:
            self.assertEqual(self.plug.get_emeter_daily(year=1900, month=1),
                             {})

            d = self.plug.get_emeter_daily()
            if len(d) < 1:
                print("no emeter daily information, skipping..")
                return
            k, v = d.popitem()
            self.assertTrue(isinstance(k, int))
            self.assertTrue(isinstance(v, float))
        else:
            self.assertEqual(self.plug.get_emeter_daily(year=1900, month=1),
                             None)

    def test_get_emeter_monthly(self):
        if self.plug.has_emeter:
            self.assertEqual(self.plug.get_emeter_monthly(year=1900), {})

            d = self.plug.get_emeter_monthly()
            if len(d) < 1:
                print("no emeter monthly information, skipping..")
                return
            k, v = d.popitem()
            self.assertTrue(isinstance(k, int))
            self.assertTrue(isinstance(v, float))
        else:
            self.assertEqual(self.plug.get_emeter_monthly(year=1900), None)

    @skip("not clearing your stats..")
    def test_erase_emeter_stats(self):
        self.fail()

    def test_current_consumption(self):
        if self.plug.has_emeter:
            x = self.plug.current_consumption()
            self.assertTrue(isinstance(x, float))
            self.assertTrue(x >= 0.0)
        else:
            self.assertEqual(self.plug.current_consumption(), None)

    def test_alias(self):
        test_alias = "TEST1234"
        original = self.plug.alias
        self.assertTrue(isinstance(original, str))
        self.plug.alias = test_alias
        self.assertEqual(self.plug.alias, test_alias)
        self.plug.alias = original
        self.assertEqual(self.plug.alias, original)

    def test_led(self):
        original = self.plug.led

        self.plug.led = False
        self.assertFalse(self.plug.led)
        self.plug.led = True
        self.assertTrue(self.plug.led)

        self.plug.led = original

    def test_icon(self):
        self.assertEqual(set(self.plug.icon.keys()), {'icon', 'hash'})

    def test_time(self):
        self.assertTrue(isinstance(self.plug.time, datetime.datetime))
        # TODO check setting?

    def test_timezone(self):
        self.tz_schema(self.plug.timezone)

    def test_hw_info(self):
        self.sysinfo_schema(self.plug.hw_info)

    def test_on_since(self):
        self.assertTrue(isinstance(self.plug.on_since, datetime.datetime))

    def test_location(self):
        self.sysinfo_schema(self.plug.location)

    def test_rssi(self):
        self.sysinfo_schema({'rssi': self.plug.rssi})  # wrapping for vol

    def test_mac(self):
        self.sysinfo_schema({'mac': self.plug.mac})  # wrapping for val
        # TODO check setting?

    def test_repr(self):
        repr(self.plug)


class TestSmartPlugHS110(TestSmartPlugHS100):
    SYSINFO = sysinfo_hs110

    def test_emeter_upcast(self):
        emeter = self.plug.get_emeter_realtime()
        self.assertAlmostEqual(emeter["power"] * 10**3, emeter["power_mw"])
        self.assertAlmostEqual(emeter["voltage"] * 10**3, emeter["voltage_mv"])
        self.assertAlmostEqual(emeter["current"] * 10**3, emeter["current_ma"])
        self.assertAlmostEqual(emeter["total"] * 10**3, emeter["total_wh"])

    def test_emeter_daily_upcast(self):
        emeter = self.plug.get_emeter_daily()
        _, v = emeter.popitem()

        emeter = self.plug.get_emeter_daily(kwh=False)
        _, v2 = emeter.popitem()

        self.assertAlmostEqual(v * 10**3, v2)

    def test_get_emeter_monthly_upcast(self):
        emeter = self.plug.get_emeter_monthly()
        _, v = emeter.popitem()

        emeter = self.plug.get_emeter_monthly(kwh=False)
        _, v2 = emeter.popitem()

        self.assertAlmostEqual(v * 10**3, v2)


class TestSmartPlugHS110_HW2(TestSmartPlugHS100):
    SYSINFO = sysinfo_hs110_au_v2

    def test_emeter_downcast(self):
        emeter = self.plug.get_emeter_realtime()
        self.assertAlmostEqual(emeter["power"], emeter["power_mw"] / 10**3)
        self.assertAlmostEqual(emeter["voltage"], emeter["voltage_mv"] / 10**3)
        self.assertAlmostEqual(emeter["current"], emeter["current_ma"] / 10**3)
        self.assertAlmostEqual(emeter["total"], emeter["total_wh"] / 10**3)

    def test_emeter_daily_downcast(self):
        emeter = self.plug.get_emeter_daily()
        _, v = emeter.popitem()

        emeter = self.plug.get_emeter_daily(kwh=False)
        _, v2 = emeter.popitem()

        self.assertAlmostEqual(v * 10**3, v2)

    def test_get_emeter_monthly_downcast(self):
        emeter = self.plug.get_emeter_monthly()
        _, v = emeter.popitem()

        emeter = self.plug.get_emeter_monthly(kwh=False)
        _, v2 = emeter.popitem()

        self.assertAlmostEqual(v * 10**3, v2)


class TestSmartPlugHS200(TestSmartPlugHS100):
    SYSINFO = sysinfo_hs200


class TestSmartPlugHS105(TestSmartPlugHS100):
    SYSINFO = sysinfo_hs105

    def test_location_i(self):
        if PLUG_IP is not None:
            plug_i = SmartPlug(PLUG_IP)
        else:
            plug_i = SmartPlug("127.0.0.1",
                               protocol=FakeTransportProtocol(self.SYSINFO))

        self.sysinfo_schema(plug_i.location)


class TestSmartPlugHS220(TestSmartPlugHS105):
    """HS220 with dimming functionality. Sysinfo looks similar to HS105."""
    SYSINFO = sysinfo_hs220

    def test_dimmable(self):
        assert self.plug.is_dimmable
        assert self.plug.brightness == 25
        self.plug.brightness = 100
        assert self.plug.brightness == 100

        with self.assertRaises(ValueError):
            self.plug.brightness = 110

        with self.assertRaises(ValueError):
            self.plug.brightness = -1

        with self.assertRaises(ValueError):
            self.plug.brightness = "foo"

        with self.assertRaises(ValueError):
            self.plug.brightness = 11.1
