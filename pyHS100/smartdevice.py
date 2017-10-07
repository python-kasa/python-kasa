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
import datetime
import logging
import socket
import warnings
from collections import defaultdict
from typing import Any, Dict, List, Tuple, Optional

from .protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class SmartDeviceException(Exception):
    """
    SmartDeviceException gets raised for errors reported by device.
    """
    pass


class SmartDevice(object):
    # possible device features
    FEATURE_ENERGY_METER = 'ENE'
    FEATURE_TIMER = 'TIM'

    ALL_FEATURES = (FEATURE_ENERGY_METER, FEATURE_TIMER)

    def __init__(self,
                 ip_address: str,
                 protocol: Optional[TPLinkSmartHomeProtocol] = None) -> None:
        """
        Create a new SmartDevice instance, identified through its IP address.

        :param str ip_address: ip address on which the device listens
        """
        socket.inet_pton(socket.AF_INET, ip_address)
        self.ip_address = ip_address
        if not protocol:
            protocol = TPLinkSmartHomeProtocol()
        self.protocol = protocol
        self.emeter_type = "emeter"  # type: str
        self.emeter_units = False

    def _query_helper(self,
                      target: str,
                      cmd: str,
                      arg: Optional[Dict] = None) -> Any:
        """
        Helper returning unwrapped result object and doing error handling.

        :param target: Target system {system, time, emeter, ..}
        :param cmd: Command to execute
        :param arg: JSON object passed as parameter to the command
        :return: Unwrapped result for the call.
        :rtype: dict
        :raises SmartDeviceException: if command was not executed correctly
        """
        if arg is None:
            arg = {}
        try:
            response = self.protocol.query(
                host=self.ip_address,
                request={target: {cmd: arg}}
            )
        except Exception as ex:
            raise SmartDeviceException('Communication error') from ex

        if target not in response:
            raise SmartDeviceException("No required {} in response: {}"
                                       .format(target, response))

        result = response[target]
        if "err_code" in result and result["err_code"] != 0:
            raise SmartDeviceException("Error on {}.{}: {}"
                                       .format(target, cmd, result))

        result = result[cmd]
        del result["err_code"]

        return result

    @property
    def features(self) -> List[str]:
        """
        Returns features of the devices

        :return: list of features
        :rtype: list
        """
        warnings.simplefilter('always', DeprecationWarning)
        warnings.warn(
            "features works only on plugs and its use is discouraged, "
            "and it will likely to be removed at some point",
            DeprecationWarning,
            stacklevel=2
        )
        warnings.simplefilter('default', DeprecationWarning)
        if "feature" not in self.sys_info:
            return []

        features = self.sys_info['feature'].split(':')

        for feature in features:
            if feature not in SmartDevice.ALL_FEATURES:
                _LOGGER.warning("Unknown feature %s on device %s.",
                                feature, self.model)

        return features

    @property
    def has_emeter(self) -> bool:
        """
        Checks feature list for energy meter support.
        Note: this has to be implemented on a device specific class.

        :return: True if energey meter is available
                 False if energymeter is missing
        """
        raise NotImplementedError()

    @property
    def sys_info(self) -> Dict[str, Any]:
        """
        Returns the complete system information from the device.

        :return: System information dict.
        :rtype: dict
        """
        return defaultdict(lambda: None, self.get_sysinfo())

    def get_sysinfo(self) -> Dict:
        """
        Retrieve system information.

        :return: sysinfo
        :rtype dict
        :raises SmartDeviceException: on error
        """
        return self._query_helper("system", "get_sysinfo")

    def identify(self) -> Tuple[str, str, Any]:
        """
        Query device information to identify model and featureset

        :return: (alias, model, list of supported features)
        :rtype: tuple
        """
        warnings.simplefilter('always', DeprecationWarning)
        warnings.warn(
            "use alias and model instead of idenfity()",
            DeprecationWarning,
            stacklevel=2
        )
        warnings.simplefilter('default', DeprecationWarning)

        info = self.sys_info

        #  TODO sysinfo parsing should happen in sys_info
        #  to avoid calling fetch here twice..
        return info["alias"], info["model"], self.features

    @property
    def model(self) -> str:
        """
        Get model of the device

        :return: device model
        :rtype: str
        :raises SmartDeviceException: on error
        """
        return str(self.sys_info['model'])

    @property
    def alias(self) -> str:
        """
        Get current device alias (name)

        :return: Device name aka alias.
        :rtype: str
        """
        return str(self.sys_info['alias'])

    @alias.setter
    def alias(self, alias: str) -> None:
        """
        Sets the device name aka alias.

        :param alias: New alias (name)
        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_dev_alias", {"alias": alias})

    @property
    def icon(self) -> Dict:
        """
        Returns device icon

        Note: not working on HS110, but is always empty.

        :return: icon and its hash
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        return self._query_helper("system", "get_dev_icon")

    @icon.setter
    def icon(self, icon: str) -> None:
        """
        Content for hash and icon are unknown.

        :param str icon: Icon path(?)
        :raises NotImplementedError: when not implemented
        :raises SmartPlugError: on error
        """
        raise NotImplementedError()
        # here just for the sake of completeness
        # self._query_helper("system",
        #                    "set_dev_icon", {"icon": "", "hash": ""})
        # self.initialize()

    @property
    def time(self) -> Optional[datetime.datetime]:
        """
        Returns current time from the device.

        :return: datetime for device's time
        :rtype: datetime.datetime or None when not available
        :raises SmartDeviceException: on error
        """
        try:
            res = self._query_helper("time", "get_time")
            return datetime.datetime(res["year"], res["month"], res["mday"],
                                     res["hour"], res["min"], res["sec"])
        except SmartDeviceException:
            return None

    @time.setter
    def time(self, ts: datetime.datetime) -> None:
        """
        Sets time based on datetime object.
        Note: this calls set_timezone() for setting.

        :param datetime.datetime ts: New date and time
        :return: result
        :type: dict
        :raises NotImplemented: when not implemented.
        :raises SmartDeviceException: on error
        """
        raise NotImplementedError("Fails with err_code == 0 with HS110.")
        """
        here just for the sake of completeness.
        if someone figures out why it doesn't work,
        please create a PR :-)
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
    def timezone(self) -> Dict:
        """
        Returns timezone information

        :return: Timezone information
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        return self._query_helper("time", "get_timezone")

    @property
    def hw_info(self) -> Dict:
        """
        Returns information about hardware

        :return: Information about hardware
        :rtype: dict
        """
        keys = ["sw_ver", "hw_ver", "mac", "mic_mac", "type",
                "mic_type", "hwId", "fwId", "oemId", "dev_name"]
        info = self.sys_info
        return {key: info[key] for key in keys if key in info}

    @property
    def location(self) -> Dict:
        """
        Location of the device, as read from sysinfo

        :return: latitude and longitude
        :rtype: dict
        """
        info = self.sys_info
        loc = {"latitude": None,
               "longitude": None}

        if "latitude" in info and "longitude" in info:
            loc["latitude"] = info["latitude"]
            loc["longitude"] = info["longitude"]
        elif "latitude_i" in info and "longitude_i" in info:
            loc["latitude"] = info["latitude_i"]
            loc["longitude"] = info["longitude_i"]
        else:
            _LOGGER.warning("Unsupported device location.")

        return loc

    @property
    def rssi(self) -> Optional[int]:
        """
        Returns WiFi signal strenth (rssi)

        :return: rssi
        :rtype: int
        """
        if "rssi" in self.sys_info:
            return int(self.sys_info["rssi"])
        return None

    @property
    def mac(self) -> str:
        """
        Returns mac address

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :rtype: str
        """
        info = self.sys_info

        if 'mac' in info:
            return str(info["mac"])
        elif 'mic_mac' in info:
            return str(info['mic_mac'])
        else:
            raise SmartDeviceException("Unknown mac, please submit a bug"
                                       "with sysinfo output.")

    @mac.setter
    def mac(self, mac: str) -> None:
        """
        Sets new mac address

        :param str mac: mac in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_mac_addr", {"mac": mac})

    def get_emeter_realtime(self) -> Optional[Dict]:
        """
        Retrive current energy readings from device.

        :returns: current readings or False
        :rtype: dict, None
                  None if device has no energy meter or error occured
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            return None

        return self._query_helper(self.emeter_type, "get_realtime")

    def get_emeter_daily(self,
                         year: int = None,
                         month: int = None) -> Optional[Dict]:
        """
        Retrieve daily statistics for a given month

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistcs (default: this
                      month)
        :return: mapping of day of month to value
                 None if device has no energy meter or error occured
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            return None

        if year is None:
            year = datetime.datetime.now().year
        if month is None:
            month = datetime.datetime.now().month

        response = self._query_helper(self.emeter_type, "get_daystat",
                                      {'month': month, 'year': year})

        if self.emeter_units:
            key = 'energy_wh'
        else:
            key = 'energy'

        return {entry['day']: entry[key]
                for entry in response['day_list']}

    def get_emeter_monthly(self, year=None) -> Optional[Dict]:
        """
        Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :return: dict: mapping of month to value
                 None if device has no energy meter
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            return None

        if year is None:
            year = datetime.datetime.now().year

        response = self._query_helper(self.emeter_type, "get_monthstat",
                                      {'year': year})

        if self.emeter_units:
            key = 'energy_wh'
        else:
            key = 'energy'

        return {entry['month']: entry[key]
                for entry in response['month_list']}

    def erase_emeter_stats(self) -> bool:
        """
        Erase energy meter statistics

        :return: True if statistics were deleted
                 False if device has no energy meter.
        :rtype: bool
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            return False

        self._query_helper(self.emeter_type, "erase_emeter_stat", None)

        # As query_helper raises exception in case of failure, we have
        # succeeded when we are this far.
        return True

    def current_consumption(self) -> Optional[float]:
        """
        Get the current power consumption in Watt.

        :return: the current power consumption in Watt.
                 None if device has no energy meter.
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            return None

        response = self.get_emeter_realtime()
        if self.emeter_units:
            return float(response['power_mw'])
        else:
            return float(response['power'])

    def turn_off(self) -> None:
        """
        Turns the device off.
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    @property
    def is_off(self) -> bool:
        """
        Returns whether device is off.

        :return: True if device is off, False otherwise.
        :rtype: bool
        """
        return not self.is_on

    def turn_on(self) -> None:
        """
        Turns the device on.
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    @property
    def is_on(self) -> bool:
        """
        Returns whether the device is on.

        :return: True if the device is on, False otherwise.
        :rtype: bool
        :return:
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    @property
    def state_information(self) -> Dict[str, Any]:
        """
        Returns device-type specific, end-user friendly state information.
        :return: dict with state information.
        :rtype: dict
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    def __repr__(self):
        return "<%s at %s (%s), is_on: %s - dev specific: %s>" % (
            self.__class__.__name__,
            self.ip_address,
            self.alias,
            self.is_on,
            self.state_information)
