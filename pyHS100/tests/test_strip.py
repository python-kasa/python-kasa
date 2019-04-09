from unittest import TestCase, skip
from voluptuous import Schema, All, Any, Range, Coerce
import datetime

from .. import SmartStrip, SmartPlug, SmartStripException, SmartDeviceException
from .fakes import FakeTransportProtocol, sysinfo_hs300
from .test_pyHS100 import check_mac, check_int_bool

# Set IP instead of None if you want to run tests on a device.
STRIP_IP = None


class TestSmartStripHS300(TestCase):
    SYSINFO = sysinfo_hs300  # type: Dict
    # these schemas should go to the mainlib as
    # they can be useful when adding support for new features/devices
    # as well as to check that faked devices are operating properly.
    sysinfo_schema = Schema({
        "sw_ver": str,
        "hw_ver": str,
        "model": str,
        "deviceId": str,
        "oemId": str,
        "hwId": str,
        "rssi": Any(int, None),  # rssi can also be positive, see #54
        "longitude": Any(All(int, Range(min=-1800000, max=1800000)), None),
        "latitude": Any(All(int, Range(min=-900000, max=900000)), None),
        "longitude_i": Any(All(int, Range(min=-1800000, max=1800000)), None),
        "latitude_i": Any(All(int, Range(min=-900000, max=900000)), None),
        "alias": str,
        "mic_type": str,
        "feature": str,
        "mac": check_mac,
        "updating": check_int_bool,
        "led_off": check_int_bool,
        "children": [{
            "id": str,
            "state": int,
            "alias": str,
            "on_time": int,
            "next_action": {"type": int},
        }],
        "child_num": int,
        "err_code": int,
    })

    current_consumption_schema = Schema(
        Any(
            {
                "voltage": Any(All(float, Range(min=0, max=300)), None),
                "power": Any(Coerce(float, Range(min=0)), None),
                "total": Any(Coerce(float, Range(min=0)), None),
                "current": Any(All(float, Range(min=0)), None),

                "voltage_mv": Any(All(int, Range(min=0, max=300000)), None),
                "power_mw": Any(Coerce(int, Range(min=0)), None),
                "total_wh": Any(Coerce(int, Range(min=0)), None),
                "current_ma": Any(All(int, Range(min=0)), None),
            },
            None
        )
    )

    tz_schema = Schema({
        "zone_str": str,
        "dst_offset": int,
        "index": All(int, Range(min=0)),
        "tz_str": str,
    })

    def setUp(self):
        if STRIP_IP is not None:
            self.strip = SmartStrip(STRIP_IP)
        else:
            self.strip = SmartStrip(
                host="127.0.0.1",
                protocol=FakeTransportProtocol(self.SYSINFO)
            )

    def tearDown(self):
        self.strip = None

    def test_initialize(self):
        self.assertIsNotNone(self.strip.sys_info)
        self.assertTrue(self.strip.num_children)
        self.sysinfo_schema(self.strip.sys_info)

    def test_initialize_invalid_connection(self):
        with self.assertRaises(SmartDeviceException):
            SmartStrip(
                host="127.0.0.1",
                protocol=FakeTransportProtocol(self.SYSINFO, invalid=True))

    def test_query_helper(self):
        with self.assertRaises(SmartDeviceException):
            self.strip._query_helper("test", "testcmd", {})

    def test_raise_for_index(self):
        with self.assertRaises(SmartStripException):
            self.strip.raise_for_index(index=self.strip.num_children + 100)

    def test_state_strip(self):
        with self.assertRaises(ValueError):
            self.strip.state = 1234
        with self.assertRaises(ValueError):
            self.strip.state = "1234"
        with self.assertRaises(ValueError):
            self.strip.state = True

        orig_state = self.strip.state
        if orig_state == SmartPlug.SWITCH_STATE_OFF:
            self.strip.state = "ON"
            self.assertTrue(self.strip.state == SmartPlug.SWITCH_STATE_ON)
            self.strip.state = "OFF"
            self.assertTrue(self.strip.state == SmartPlug.SWITCH_STATE_OFF)
        elif orig_state == SmartPlug.SWITCH_STATE_ON:
            self.strip.state = "OFF"
            self.assertTrue(self.strip.state == SmartPlug.SWITCH_STATE_OFF)
            self.strip.state = "ON"
            self.assertTrue(self.strip.state == SmartPlug.SWITCH_STATE_ON)
        elif orig_state == SmartPlug.SWITCH_STATE_UNKNOWN:
            self.fail("can't test for unknown state")

    def test_state_plugs(self):
        # value errors
        for plug_index in range(self.strip.num_children):
            with self.assertRaises(ValueError):
                self.strip.set_state(value=1234, index=plug_index)

            with self.assertRaises(ValueError):
                self.strip.set_state(value="1234", index=plug_index)

            with self.assertRaises(ValueError):
                self.strip.set_state(value=True, index=plug_index)

        # out of bounds error
        with self.assertRaises(SmartStripException):
            self.strip.set_state(
                value=SmartPlug.SWITCH_STATE_ON,
                index=self.strip.num_children + 100
            )

        # on off
        for plug_index in range(self.strip.num_children):
            orig_state = self.strip.state[plug_index]
            if orig_state == SmartPlug.SWITCH_STATE_OFF:
                self.strip.set_state(value="ON", index=plug_index)
                self.assertTrue(
                    self.strip.state[plug_index] == SmartPlug.SWITCH_STATE_ON)
                self.strip.set_state(value="OFF", index=plug_index)
                self.assertTrue(
                    self.strip.state[plug_index] == SmartPlug.SWITCH_STATE_OFF)
            elif orig_state == SmartPlug.SWITCH_STATE_ON:
                self.strip.set_state(value="OFF", index=plug_index)
                self.assertTrue(
                    self.strip.state[plug_index] == SmartPlug.SWITCH_STATE_OFF)
                self.strip.set_state(value="ON", index=plug_index)
                self.assertTrue(
                    self.strip.state[plug_index] == SmartPlug.SWITCH_STATE_ON)
            elif orig_state == SmartPlug.SWITCH_STATE_UNKNOWN:
                self.fail("can't test for unknown state")

    def test_turns_and_isses(self):
        # all on
        self.strip.turn_on()
        for index, state in self.strip.is_on().items():
            self.assertTrue(state)
            self.assertTrue(self.strip.is_on(index=index) == state)

        # all off
        self.strip.turn_off()
        for index, state in self.strip.is_on().items():
            self.assertFalse(state)
            self.assertTrue(self.strip.is_on(index=index) == state)

        # individual on
        for plug_index in range(self.strip.num_children):
            original_states = self.strip.is_on()
            self.strip.turn_on(index=plug_index)

            # only target outlet should have state changed
            for index, state in self.strip.is_on().items():
                if index == plug_index:
                    self.assertTrue(state != original_states[index])
                else:
                    self.assertTrue(state == original_states[index])

        # individual off
        for plug_index in range(self.strip.num_children):
            original_states = self.strip.is_on()
            self.strip.turn_off(index=plug_index)

            # only target outlet should have state changed
            for index, state in self.strip.is_on().items():
                if index == plug_index:
                    self.assertTrue(state != original_states[index])
                else:
                    self.assertTrue(state == original_states[index])

        # out of bounds
        with self.assertRaises(SmartStripException):
            self.strip.turn_off(index=self.strip.num_children + 100)
        with self.assertRaises(SmartStripException):
            self.strip.turn_on(index=self.strip.num_children + 100)
        with self.assertRaises(SmartStripException):
            self.strip.is_on(index=self.strip.num_children + 100)

    @skip("this test will wear out your relays")
    def test_all_binary_states(self):
        # test every binary state
        for state in range(2 ** self.strip.num_children):

            # create binary state map
            state_map = {}
            for plug_index in range(self.strip.num_children):
                state_map[plug_index] = bool((state >> plug_index) & 1)

                if state_map[plug_index]:
                    self.strip.turn_on(index=plug_index)
                else:
                    self.strip.turn_off(index=plug_index)

            # check state map applied
            for index, state in self.strip.is_on().items():
                self.assertTrue(state_map[index] == state)

            # toggle each outlet with state map applied
            for plug_index in range(self.strip.num_children):

                # toggle state
                if state_map[plug_index]:
                    self.strip.turn_off(index=plug_index)
                else:
                    self.strip.turn_on(index=plug_index)

                # only target outlet should have state changed
                for index, state in self.strip.is_on().items():
                    if index == plug_index:
                        self.assertTrue(state != state_map[index])
                    else:
                        self.assertTrue(state == state_map[index])

                # reset state
                if state_map[plug_index]:
                    self.strip.turn_on(index=plug_index)
                else:
                    self.strip.turn_off(index=plug_index)

                # original state map should be restored
                for index, state in self.strip.is_on().items():
                    self.assertTrue(state == state_map[index])

    def test_has_emeter(self):
        # a not so nice way for checking for emeter availability..
        if "HS300" in self.strip.sys_info["model"]:
            self.assertTrue(self.strip.has_emeter)
        else:
            self.assertFalse(self.strip.has_emeter)

    def test_get_emeter_realtime(self):
        if self.strip.has_emeter:
            # test with index
            for plug_index in range(self.strip.num_children):
                emeter = self.strip.get_emeter_realtime(index=plug_index)
                self.current_consumption_schema(emeter)

            # test without index
            for index, emeter in self.strip.get_emeter_realtime().items():
                self.current_consumption_schema(emeter)

            # out of bounds
            with self.assertRaises(SmartStripException):
                self.strip.get_emeter_realtime(
                    index=self.strip.num_children + 100
                )
        else:
            self.assertEqual(self.strip.get_emeter_realtime(), None)

    def test_get_emeter_daily(self):
        if self.strip.has_emeter:
            # test with index
            for plug_index in range(self.strip.num_children):
                emeter = self.strip.get_emeter_daily(year=1900, month=1,
                                                     index=plug_index)
                self.assertEqual(emeter, {})
                if len(emeter) < 1:
                    print("no emeter daily information, skipping..")
                    return
                k, v = emeter.popitem()
                self.assertTrue(isinstance(k, int))
                self.assertTrue(isinstance(v, float))

            # test without index
            all_emeter = self.strip.get_emeter_daily(year=1900, month=1)
            for index, emeter in all_emeter.items():
                self.assertEqual(emeter, {})
                if len(emeter) < 1:
                    print("no emeter daily information, skipping..")
                    return
                k, v = emeter.popitem()
                self.assertTrue(isinstance(k, int))
                self.assertTrue(isinstance(v, float))

            # out of bounds
            with self.assertRaises(SmartStripException):
                self.strip.get_emeter_daily(
                    year=1900,
                    month=1,
                    index=self.strip.num_children + 100
                )
        else:
            self.assertEqual(
                self.strip.get_emeter_daily(year=1900, month=1), None)

    def test_get_emeter_monthly(self):
        if self.strip.has_emeter:
            # test with index
            for plug_index in range(self.strip.num_children):
                emeter = self.strip.get_emeter_monthly(year=1900,
                                                       index=plug_index)
                self.assertEqual(emeter, {})
                if len(emeter) < 1:
                    print("no emeter daily information, skipping..")
                    return
                k, v = emeter.popitem()
                self.assertTrue(isinstance(k, int))
                self.assertTrue(isinstance(v, float))

            # test without index
            all_emeter = self.strip.get_emeter_monthly(year=1900)
            for index, emeter in all_emeter.items():
                self.assertEqual(emeter, {})
                if len(emeter) < 1:
                    print("no emeter daily information, skipping..")
                    return
                k, v = emeter.popitem()
                self.assertTrue(isinstance(k, int))
                self.assertTrue(isinstance(v, float))

            # out of bounds
            with self.assertRaises(SmartStripException):
                self.strip.get_emeter_monthly(
                    year=1900,
                    index=self.strip.num_children + 100
                )
        else:
            self.assertEqual(self.strip.get_emeter_monthly(year=1900), None)

    @skip("not clearing your stats..")
    def test_erase_emeter_stats(self):
        self.fail()

    def test_current_consumption(self):
        if self.strip.has_emeter:
            # test with index
            for plug_index in range(self.strip.num_children):
                emeter = self.strip.current_consumption(index=plug_index)
                self.assertTrue(isinstance(emeter, float))
                self.assertTrue(emeter >= 0.0)

            # test without index
            for index, emeter in self.strip.current_consumption().items():
                self.assertTrue(isinstance(emeter, float))
                self.assertTrue(emeter >= 0.0)

            # out of bounds
            with self.assertRaises(SmartStripException):
                self.strip.current_consumption(
                    index=self.strip.num_children + 100
                )
        else:
            self.assertEqual(self.strip.current_consumption(), None)

    def test_alias(self):
        test_alias = "TEST1234"

        # strip alias
        original = self.strip.alias
        self.assertTrue(isinstance(original, str))
        self.strip.alias = test_alias
        self.assertEqual(self.strip.alias, test_alias)
        self.strip.alias = original
        self.assertEqual(self.strip.alias, original)

        # plug alias
        original = self.strip.get_alias()
        for plug in range(self.strip.num_children):
            self.strip.set_alias(alias=test_alias, index=plug)
            self.assertEqual(self.strip.get_alias(index=plug), test_alias)
            self.strip.set_alias(alias=original[plug], index=plug)
            self.assertEqual(self.strip.get_alias(index=plug), original[plug])

    def test_led(self):
        original = self.strip.led

        self.strip.led = False
        self.assertFalse(self.strip.led)
        self.strip.led = True
        self.assertTrue(self.strip.led)
        self.strip.led = original

    def test_icon(self):
        with self.assertRaises(NotImplementedError):
            self.strip.icon

    def test_time(self):
        self.assertTrue(isinstance(self.strip.time, datetime.datetime))
        # TODO check setting?

    def test_timezone(self):
        self.tz_schema(self.strip.timezone)

    def test_hw_info(self):
        self.sysinfo_schema(self.strip.hw_info)

    def test_on_since(self):
        # out of bounds
        with self.assertRaises(SmartStripException):
            self.strip.on_since(index=self.strip.num_children + 1)

        # individual on_since
        for plug_index in range(self.strip.num_children):
            self.assertTrue(isinstance(
                self.strip.on_since(index=plug_index), datetime.datetime))

        # all on_since
        for index, plug_on_since in self.strip.on_since().items():
            self.assertTrue(isinstance(plug_on_since, datetime.datetime))

    def test_location(self):
        print(self.strip.location)
        self.sysinfo_schema(self.strip.location)

    def test_rssi(self):
        self.sysinfo_schema({'rssi': self.strip.rssi})  # wrapping for vol

    def test_mac(self):
        self.sysinfo_schema({'mac': self.strip.mac})  # wrapping for vol

    def test_repr(self):
        repr(self.strip)
