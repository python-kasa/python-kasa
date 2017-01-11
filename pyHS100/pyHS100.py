"""
pyHS100
Python library supporting TP-Link Smart Plugs/Switches (HS100/HS110/Hs200).

The communication protocol was reverse engineered by Lubomir Stroetmann and
Tobias Esser in 'Reverse Engineering the TP-Link HS110':
https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/

This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
Stroetmann which is licensed under the Apache License, Version 2.0.

You may obtain a copy of the license at
http://www.apache.org/licenses/LICENSE-2.0
"""

# python2 compatibility
from __future__ import absolute_import
from __future__ import unicode_literals
try:
    basestring
except NameError:
    basestring = str

import datetime
import logging
import socket

from pyHS100.protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class SmartPlugException(Exception):
    """
    SmartPlugException gets raised for errors reported by the plug.
    """
    pass


class SmartPlug(object):
    """Representation of a TP-Link Smart Switch.

    Usage example when used as library:
    p = SmartPlug("192.168.1.105")
    # print the devices alias
    print(p.alias)
    # change state of plug
    p.state = "ON"
    p.state = "OFF"
    # query and print current state of plug
    print(p.state)

    Errors reported by the device are raised as SmartPlugExceptions,
    and should be handled by the user of the library.

    Note:
    The library references the same structure as defined for the D-Link Switch
    """
    # switch states
    SWITCH_STATE_ON = 'ON'
    SWITCH_STATE_OFF = 'OFF'
    SWITCH_STATE_UNKNOWN = 'UNKNOWN'

    # possible device features
    FEATURE_ENERGY_METER = 'ENE'
    FEATURE_TIMER = 'TIM'

    ALL_FEATURES = (FEATURE_ENERGY_METER, FEATURE_TIMER)

    def __init__(self, ip_address, protocol=None):
        """
        Create a new SmartPlug instance, identified through its IP address.

        :param str ip_address: ip address on which the device listens
        :raises SmartPlugException: when unable to communicate with the device
        """
        socket.inet_pton(socket.AF_INET, ip_address)
        self.ip_address = ip_address
        if not protocol:
            protocol = TPLinkSmartHomeProtocol()
        self.protocol = protocol

    def _query_helper(self, target, cmd, arg={}):
        """
        Helper returning unwrapped result object and doing error handling.

        :param target: Target system {system, time, emeter, ..}
        :param cmd: Command to execute
        :param arg: JSON object passed as parameter to the command, defaults to {}
        :return: Unwrapped result for the call.
        :rtype: dict
        :raises SmartPlugException: if command was not executed correctly
        """

        try:
            response = self.protocol.query(
                host=self.ip_address,
                request={target: {cmd: arg}}
            )
        except Exception as ex:
            raise SmartPlugException(ex) from ex

        if target not in response:
            raise SmartPlugException("No required {} in response: {}".format(target, response))

        result = response[target]
        if "err_code" in result and result["err_code"] != 0:
            raise SmartPlugException("Error on {}.{}: {}".format(target, cmd, result))

        result = result[cmd]
        del result["err_code"]

        return result

    @property
    def sys_info(self):
        #  TODO use volyptuous
        return self.get_sysinfo()

    @property
    def state(self):
        """
        Retrieve the switch state

        :returns: one of
                  SWITCH_STATE_ON
                  SWITCH_STATE_OFF
                  SWITCH_STATE_UNKNOWN
        :rtype: str
        """
        relay_state = self.sys_info['relay_state']

        if relay_state == 0:
            return SmartPlug.SWITCH_STATE_OFF
        elif relay_state == 1:
            return SmartPlug.SWITCH_STATE_ON
        else:
            _LOGGER.warning("Unknown state %s returned.", relay_state)
            return SmartPlug.SWITCH_STATE_UNKNOWN

    @state.setter
    def state(self, value):
        """
        Set the new switch state

        :param value: one of
                    SWITCH_STATE_ON
                    SWITCH_STATE_OFF
        :raises ValueError: on invalid state
        :raises SmartPlugException: on error

        """
        if not isinstance(value, basestring):
            raise ValueError("State must be str, not of %s.", type(value))
        elif value.upper() == SmartPlug.SWITCH_STATE_ON:
            self.turn_on()
        elif value.upper() == SmartPlug.SWITCH_STATE_OFF:
            self.turn_off()
        else:
            raise ValueError("State %s is not valid.", value)

    def get_sysinfo(self):
        """
        Retrieve system information.

        :return: sysinfo
        :rtype dict
        :raises SmartPlugException: on error
        """
        return self._query_helper("system", "get_sysinfo")

    @property
    def is_on(self):
        """
        Returns whether device is on.

        :return: True if device is on, False otherwise
        """
        return bool(self.sys_info['relay_state'])

    @property
    def is_off(self):
        """
        Returns whether device is off.

        :return: True if device is off, False otherwise.
         :rtype: bool
        """
        return not self.is_on

    def turn_on(self):
        """
        Turn the switch on.

        :raises SmartPlugException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 1})

    def turn_off(self):
        """
        Turn the switch off.

        :raises SmartPlugException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 0})

    @property
    def has_emeter(self):
        """
        Checks feature list for energey meter support.

        :return: True if energey meter is available
                 False if energymeter is missing
        """
        return SmartPlug.FEATURE_ENERGY_METER in self.features

    def get_emeter_realtime(self):
        """
        Retrive current energy readings from device.

        :returns: current readings or False
        :rtype: dict, False
                  False if device has no energy meter or error occured
        :raises SmartPlugException: on error
        """
        if not self.has_emeter:
            return False

        return self._query_helper("emeter", "get_realtime")

    def get_emeter_daily(self, year=None, month=None):
        """
        Retrieve daily statistics for a given month

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistcs (default: this
                      month)
        :return: mapping of day of month to value
                 False if device has no energy meter or error occured
        :rtype: dict
        :raises SmartPlugException: on error
        """
        if not self.has_emeter:
            return False

        if year is None:
            year = datetime.datetime.now().year
        if month is None:
            month = datetime.datetime.now().month

        response = self._query_helper("emeter", "get_daystat",
                                      {'month': month, 'year': year})

        return {entry['day']: entry['energy']
                for entry in response['day_list']}

    def get_emeter_monthly(self, year=datetime.datetime.now().year):
        """
        Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :return: dict: mapping of month to value
                 False if device has no energy meter
        :rtype: dict
        :raises SmartPlugException: on error
        """
        if not self.has_emeter:
            return False

        response = self._query_helper("emeter", "get_monthstat",
                                      {'year': year})

        return {entry['month']: entry['energy']
                for entry in response['month_list']}

    def erase_emeter_stats(self):
        """
        Erase energy meter statistics

        :return: True if statistics were deleted
                 False if device has no energy meter.
        :rtype: bool
        :raises SmartPlugException: on error
        """
        if not self.has_emeter:
            return False

        self._query_helper("emeter", "erase_emeter_stat", None)

        # As query_helper raises exception in case of failure, we have succeeded when we are this far.
        return True

    def current_consumption(self):
        """
        Get the current power consumption in Watt.

        :return: the current power consumption in Watt.
                 False if device has no energy meter.
        :raises SmartPlugException: on error
        """
        if not self.has_emeter:
            return False

        response = self.get_emeter_realtime()

        return response['power']

    def identify(self):
        """
        Query device information to identify model and featureset

        :return: (alias, model, list of supported features)
        :rtype: tuple
        """

        info = self.sys_info

        #  TODO sysinfo parsing should happen in sys_info
        #  to avoid calling fetch here twice..
        return info["alias"], info["model"], self.features

    @property
    def model(self):
        """
        Get model of the device

        :return: device model
        :rtype: str
        :raises SmartPlugException: on error
        """
        return self.sys_info['model']

    @property
    def features(self):
        """
        Returns features of the devices

        :return: list of features
        :rtype: list
        """
        features = self.sys_info['feature'].split(':')

        for feature in features:
            if feature not in SmartPlug.ALL_FEATURES:
                _LOGGER.warning("Unknown feature %s on device %s.",
                                feature, self.model)

        return features

    @property
    def alias(self):
        """
        Get current device alias (name)

        :return: Device name aka alias.
        :rtype: str
        """
        return self.sys_info['alias']

    @alias.setter
    def alias(self, alias):
        """
        Sets the device name aka alias.

        :param alias: New alias (name)
        :raises SmartPlugException: on error
        """
        self._query_helper("system", "set_dev_alias", {"alias": alias})

    @property
    def led(self):
        """
        Returns the state of the led.

        :return: True if led is on, False otherwise
        :rtype: bool
        """
        return bool(1 - self.sys_info["led_off"])

    @led.setter
    def led(self, state):
        """
        Sets the state of the led (night mode)

        :param bool state: True to set led on, False to set led off
        :raises SmartPlugException: on error
        """
        self._query_helper("system", "set_led_off", {"off": int(not state)})

    @property
    def icon(self):
        """
        Returns device icon

        Note: not working on HS110, but is always empty.

        :return: icon and its hash
        :rtype: dict
        :raises SmartPlugException: on error
        """
        return self._query_helper("system", "get_dev_icon")

    @icon.setter
    def icon(self, icon):
        """
        Content for hash and icon are unknown.

        :param str icon: Icon path(?)
        :raises NotImplementedError: when not implemented
        :raises SmartPlugError: on error
        """
        raise NotImplementedError("Values for this call are unknown at this point.")
        # here just for the sake of completeness
        # self._query_helper("system", "set_dev_icon", {"icon": "", "hash": ""})
        # self.initialize()

    @property
    def time(self):
        """
        Returns current time from the device.

        :return: datetime for device's time
        :rtype: datetime.datetime
        :raises SmartPlugException: on error
        """
        res = self._query_helper("time", "get_time")
        return datetime.datetime(res["year"], res["month"], res["mday"],
                                 res["hour"], res["min"], res["sec"])

    @time.setter
    def time(self, ts):
        """
        Sets time based on datetime object.
        Note: this calls set_timezone() for setting.

        :param datetime.datetime ts: New date and time
        :return: result
        :type: dict
        :raises NotImplemented: when not implemented.
        :raises SmartPlugException: on error
        """
        raise NotImplementedError("Fails with err_code == 0 with HS110.")
        """ here just for the sake of completeness / if someone figures out why it doesn't work.
        ts_obj = {
            "index": self.timezone["index"],
            "hour": ts.hour,
            "min": ts.minute,
            "sec": ts.second,
            "year": ts.year,
            "month": ts.month,
            "mday": ts.day,
        }


        response = self._query_helper("time", "set_timezone", ts_obj)
        self.initialize()

        return response
        """

    @property
    def timezone(self):
        """
        Returns timezone information

        :return: Timezone information
        :rtype: dict
        :raises SmartPlugException: on error
        """
        return self._query_helper("time", "get_timezone")

    @property
    def hw_info(self):
        """
        Returns information about hardware

        :return: Information about hardware
        :rtype: dict
        """
        keys = ["sw_ver", "hw_ver", "mac", "hwId", "fwId", "oemId", "dev_name"]
        info = self.sys_info
        return {key: info[key] for key in keys}

    @property
    def on_since(self):
        """
        Returns pretty-printed on-time

        :return: datetime for on since
        :rtype: datetime
        """
        return datetime.datetime.now() - \
               datetime.timedelta(seconds=self.sys_info["on_time"])

    @property
    def location(self):
        """
        Location of the device, as read from sysinfo

        :return: latitude and longitude
        :rtype: dict
        """
        info = self.sys_info
        return {"latitude": info["latitude"],
                "longitude": info["longitude"]}

    @property
    def rssi(self):
        """
        Returns WiFi signal strenth (rssi)

        :return: rssi
        :rtype: int
        """
        return self.sys_info["rssi"]

    @property
    def mac(self):
        """
        Returns mac address

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :rtype: str
        """
        return self.sys_info["mac"]

    @mac.setter
    def mac(self, mac):
        """
        Sets new mac address

        :param str mac: mac in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :raises SmartPlugException: on error
        """
        self._query_helper("system", "set_mac_addr", {"mac": mac})
