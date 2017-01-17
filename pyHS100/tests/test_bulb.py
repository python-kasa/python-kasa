from __future__ import absolute_import
from __future__ import unicode_literals

from unittest import TestCase, skip, skipIf
from voluptuous import Schema, Invalid, All, Range
from functools import partial

from pyHS100 import SmartBulb, SmartPlugException
from pyHS100.tests.fakes import FakeTransportProtocol, sysinfo_lb130

BULB_IP = '192.168.250.186'
SKIP_STATE_TESTS = False

# python2 compatibility
try:
    basestring
except NameError:
    basestring = str


def check_int_bool(x):
    if x != 0 and x != 1:
        raise Invalid(x)
    return x


def check_mode(x):
    if x in ['schedule', 'none']:
        return x

    raise Invalid("invalid mode {}".format(x))


class TestSmartBulb(TestCase):
    # these schemas should go to the mainlib as
    # they can be useful when adding support for new features/devices
    # as well as to check that faked devices are operating properly.
    sysinfo_schema = Schema({
        'active_mode': check_mode,
        'alias': basestring,
        'ctrl_protocols': {
            'name': basestring,
            'version': basestring,
        },
        'description': basestring,
        'dev_state': basestring,
        'deviceId': basestring,
        'disco_ver': basestring,
        'heapsize': int,
        'hwId': basestring,
        'hw_ver': basestring,
        'is_color': check_int_bool,
        'is_dimmable': check_int_bool,
        'is_factory': bool,
        'is_variable_color_temp': check_int_bool,
        'light_state': {
            'brightness': All(int, Range(min=0, max=100)),
            'color_temp': int,
            'hue': All(int, Range(min=0, max=255)),
            'mode': basestring,
            'on_off': check_int_bool,
            'saturation': All(int, Range(min=0, max=255)),
        },
        'mic_mac': basestring,
        'mic_type': basestring,
        'model': basestring,
        'oemId': basestring,
        'preferred_state': [{
            'brightness': All(int, Range(min=0, max=100)),
            'color_temp': int,
            'hue': All(int, Range(min=0, max=255)),
            'index': int,
            'saturation': All(int, Range(min=0, max=255)),
        }],
        'rssi': All(int, Range(max=0)),
        'sw_ver': basestring,
    })

    current_consumption_schema = Schema({
        'power_mw': int,
    })

    tz_schema = Schema({
        'zone_str': basestring,
        'dst_offset': int,
        'index': All(int, Range(min=0)),
        'tz_str': basestring,
    })

    def setUp(self):
        self.bulb = SmartBulb(BULB_IP,
                              protocol=FakeTransportProtocol(sysinfo_lb130))

    def tearDown(self):
        self.bulb = None

    def test_initialize(self):
        self.assertIsNotNone(self.bulb.sys_info)
        self.sysinfo_schema(self.bulb.sys_info)

    def test_initialize_invalid_connection(self):
        bulb = SmartBulb('127.0.0.1',
                         protocol=FakeTransportProtocol(sysinfo_lb130,
                                                        invalid=True))
        with self.assertRaises(SmartPlugException):
            bulb.sys_info['model']

    def test_query_helper(self):
        with self.assertRaises(SmartPlugException):
            self.bulb._query_helper("test", "testcmd", {})
        # TODO check for unwrapping?

    @skipIf(SKIP_STATE_TESTS, "SKIP_STATE_TESTS is True, skipping")
    def test_state(self):
        def set_invalid(x):
            self.bulb.state = x

        set_invalid_int = partial(set_invalid, 1234)
        self.assertRaises(ValueError, set_invalid_int)

        set_invalid_str = partial(set_invalid, "1234")
        self.assertRaises(ValueError, set_invalid_str)

        set_invalid_bool = partial(set_invalid, True)
        self.assertRaises(ValueError, set_invalid_bool)

        orig_state = self.bulb.state
        if orig_state == SmartBulb.BULB_STATE_OFF:
            self.bulb.state = SmartBulb.BULB_STATE_ON
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_ON)
            self.bulb.state = SmartBulb.BULB_STATE_OFF
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_OFF)
        elif orig_state == SmartBulb.BULB_STATE_ON:
            self.bulb.state = SmartBulb.BULB_STATE_OFF
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_OFF)
            self.bulb.state = SmartBulb.BULB_STATE_ON
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_ON)

    def test_get_sysinfo(self):
        # initialize checks for this already, but just to be sure
        self.sysinfo_schema(self.bulb.get_sysinfo())

    @skipIf(SKIP_STATE_TESTS, "SKIP_STATE_TESTS is True, skipping")
    def test_turns_and_isses(self):
        orig_state = self.bulb.state

        if orig_state == SmartBulb.BULB_STATE_ON:
            self.bulb.state = SmartBulb.BULB_STATE_OFF
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_OFF)
            self.bulb.state = SmartBulb.BULB_STATE_ON
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_ON)
        else:
            self.bulb.state = SmartBulb.BULB_STATE_ON
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_ON)
            self.bulb.state = SmartBulb.BULB_STATE_OFF
            self.assertTrue(self.bulb.state == SmartBulb.BULB_STATE_OFF)

    def test_get_emeter_realtime(self):
        self.current_consumption_schema((self.bulb.get_emeter_realtime()))

    def test_get_emeter_daily(self):
        self.assertEqual(self.bulb.get_emeter_daily(year=1900, month=1), {})

        k, v = self.bulb.get_emeter_daily().popitem()
        self.assertTrue(isinstance(k, int))
        self.assertTrue(isinstance(v, int))

    def test_get_emeter_monthly(self):
        self.assertEqual(self.bulb.get_emeter_monthly(year=1900), {})

        d = self.bulb.get_emeter_monthly()
        k, v = d.popitem()
        self.assertTrue(isinstance(k, int))
        self.assertTrue(isinstance(v, int))

    @skip("not clearing your stats..")
    def test_erase_emeter_stats(self):
        self.fail()

    def test_current_consumption(self):
        x = self.bulb.current_consumption()
        self.assertTrue(isinstance(x, int))
        self.assertTrue(x >= 0.0)

    def test_alias(self):
        test_alias = "TEST1234"
        original = self.bulb.alias
        self.assertTrue(isinstance(original, basestring))
        self.bulb.alias = test_alias
        self.assertEqual(self.bulb.alias, test_alias)
        self.bulb.alias = original
        self.assertEqual(self.bulb.alias, original)

    def test_icon(self):
        self.assertEqual(set(self.bulb.icon.keys()), {'icon', 'hash'})

    def test_rssi(self):
        self.sysinfo_schema({'rssi': self.bulb.rssi})  # wrapping for vol
