"""Python library supporting TP-Link Smart Home devices.

The communication protocol was reverse engineered by Lubomir Stroetmann and
Tobias Esser in 'Reverse Engineering the TP-Link HS110':
https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/

This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
Stroetmann which is licensed under the Apache License, Version 2.0.

You may obtain a copy of the license at
http://www.apache.org/licenses/LICENSE-2.0
"""
import functools
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from kasa.protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    """Device type enum."""

    Plug = 1
    Bulb = 2
    Strip = 3
    Dimmer = 4
    Unknown = -1


@dataclass
class WifiNetwork:
    """Wifi network container."""

    ssid: str
    key_type: int


class SmartDeviceException(Exception):
    """Base exception for device errors."""


class EmeterStatus(dict):
    """Container for converting different representations of emeter data.

    Newer FW/HW versions postfix the variable names with the used units,
    where-as the olders do not have this feature.

    This class automatically converts between these two to allow
    backwards and forwards compatibility.
    """

    def __getitem__(self, item):
        valid_keys = [
            "voltage_mv",
            "power_mw",
            "current_ma",
            "energy_wh",
            "total_wh",
            "voltage",
            "power",
            "current",
            "total",
            "energy",
        ]

        # 1. if requested data is available, return it
        if item in super().keys():
            return super().__getitem__(item)
        # otherwise decide how to convert it
        else:
            if item not in valid_keys:
                raise KeyError(item)
            if "_" in item:  # upscale
                return super().__getitem__(item[: item.find("_")]) * 1000
            else:  # downscale
                for i in super().keys():
                    if i.startswith(item):
                        return self.__getitem__(i) / 1000

                raise SmartDeviceException("Unable to find a value for '%s'" % item)


def requires_update(f):
    """Indicate that `update` should be called before accessing this method."""  # noqa: D202
    if inspect.iscoroutinefunction(f):

        @functools.wraps(f)
        async def wrapped(*args, **kwargs):
            self = args[0]
            assert self._sys_info is not None
            return await f(*args, **kwargs)

    else:

        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            self = args[0]
            assert self._sys_info is not None
            return f(*args, **kwargs)

    f.requires_update = True
    return wrapped


class SmartDevice:
    """Base class for all supported device types."""

    def __init__(self, host: str) -> None:
        """Create a new SmartDevice instance.

        :param str host: host name or ip address on which the device listens
        :param child_id: optional child ID for context in a parent device
        """
        self.host = host

        self.protocol = TPLinkSmartHomeProtocol()
        self.emeter_type = "emeter"
        _LOGGER.debug("Initializing %s of type %s", self.host, type(self))
        self._device_type = DeviceType.Unknown
        self._sys_info: Optional[Dict] = None

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        """Handle result unwrapping and error handling.

        :param target: Target system {system, time, emeter, ..}
        :param cmd: Command to execute
        :param arg: JSON object passed as parameter to the command
        :return: Unwrapped result for the call.
        :rtype: dict
        :raises SmartDeviceException: if command was not executed correctly
        """
        request: Dict[str, Any] = {target: {cmd: arg}}
        if child_ids is not None:
            request = {"context": {"child_ids": child_ids}, target: {cmd: arg}}

        try:
            response = await self.protocol.query(host=self.host, request=request)
        except Exception as ex:
            raise SmartDeviceException(f"Communication error on {target}:{cmd}") from ex

        if target not in response:
            raise SmartDeviceException(f"No required {target} in response: {response}")

        result = response[target]
        if "err_code" in result and result["err_code"] != 0:
            raise SmartDeviceException(f"Error on {target}.{cmd}: {result}")

        if cmd not in result:
            raise SmartDeviceException(f"No command in response: {response}")
        result = result[cmd]
        if "err_code" in result and result["err_code"] != 0:
            raise SmartDeviceException(f"Error on {target} {cmd}: {result}")

        if "err_code" in result:
            del result["err_code"]

        return result

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return whether device has an energy meter.

        :return: True if energy meter is available
                 False otherwise
        """
        sys_info = self.sys_info
        features = sys_info["feature"].split(":")
        return "ENE" in features

    async def get_sys_info(self) -> Dict[str, Any]:
        """Retrieve system information.

        :return: sysinfo
        :rtype dict
        :raises SmartDeviceException: on error
        """
        return await self._query_helper("system", "get_sysinfo")

    async def update(self):
        """Update some of the attributes.

        Needed for methods that are decorated with `requires_update`.
        """
        self._sys_info = await self.get_sys_info()

    @property  # type: ignore
    @requires_update
    def sys_info(self) -> Dict[str, Any]:
        """Retrieve system information.

        :return: sysinfo
        :rtype dict
        :raises SmartDeviceException: on error
        """
        assert self._sys_info is not None
        return self._sys_info

    @property  # type: ignore
    @requires_update
    def model(self) -> str:
        """Return device model.

        :return: device model
        :rtype: str
        :raises SmartDeviceException: on error
        """
        sys_info = self.sys_info
        return str(sys_info["model"])

    @property  # type: ignore
    @requires_update
    def alias(self) -> str:
        """Return device name (alias).

        :return: Device name aka alias.
        :rtype: str
        """
        sys_info = self.sys_info
        return str(sys_info["alias"])

    async def set_alias(self, alias: str) -> None:
        """Set the device name (alias).

        :param alias: New alias (name)
        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_dev_alias", {"alias": alias})
        await self.update()

    async def get_icon(self) -> Dict:
        """Return device icon.

        Note: not working on HS110, but is always empty.

        :return: icon and its hash
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        return await self._query_helper("system", "get_dev_icon")

    def set_icon(self, icon: str) -> None:
        """Set device icon.

        Content for hash and icon are unknown.

        :param str icon: Icon path(?)
        :raises NotImplementedError: when not implemented
        :raises SmartPlugError: on error
        """
        raise NotImplementedError()
        # here just for the sake of completeness
        # await self._query_helper("system",
        #                    "set_dev_icon", {"icon": "", "hash": ""})
        # self.initialize()

    async def get_time(self) -> Optional[datetime]:
        """Return current time from the device.

        :return: datetime for device's time
        :rtype: datetime or None when not available
        :raises SmartDeviceException: on error
        """
        try:
            res = await self._query_helper("time", "get_time")
            return datetime(
                res["year"],
                res["month"],
                res["mday"],
                res["hour"],
                res["min"],
                res["sec"],
            )
        except SmartDeviceException:
            return None

    async def set_time(self, ts: datetime) -> None:
        """Set the device time.

        Note: this calls set_timezone() for setting.

        :param datetime ts: New date and time
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


        response = await self._query_helper("time", "set_timezone", ts_obj)
        self.initialize()

        return response
        """

    async def get_timezone(self) -> Dict:
        """Return timezone information.

        :return: Timezone information
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        return await self._query_helper("time", "get_timezone")

    @property  # type: ignore
    @requires_update
    def hw_info(self) -> Dict:
        """Return hardware information.

        :return: Information about hardware
        :rtype: dict
        """
        keys = [
            "sw_ver",
            "hw_ver",
            "mac",
            "mic_mac",
            "type",
            "mic_type",
            "hwId",
            "fwId",
            "oemId",
            "dev_name",
        ]
        sys_info = self.sys_info
        return {key: sys_info[key] for key in keys if key in sys_info}

    @property  # type: ignore
    @requires_update
    def location(self) -> Dict:
        """Return geographical location.

        :return: latitude and longitude
        :rtype: dict
        """
        sys_info = self.sys_info
        loc = {"latitude": None, "longitude": None}

        if "latitude" in sys_info and "longitude" in sys_info:
            loc["latitude"] = sys_info["latitude"]
            loc["longitude"] = sys_info["longitude"]
        elif "latitude_i" in sys_info and "longitude_i" in sys_info:
            loc["latitude"] = sys_info["latitude_i"]
            loc["longitude"] = sys_info["longitude_i"]
        else:
            _LOGGER.warning("Unsupported device location.")

        return loc

    @property  # type: ignore
    @requires_update
    def rssi(self) -> Optional[int]:
        """Return WiFi signal strenth (rssi).

        :return: rssi
        :rtype: int
        """
        sys_info = self.sys_info
        if "rssi" in sys_info:
            return int(sys_info["rssi"])
        return None

    @property  # type: ignore
    @requires_update
    def mac(self) -> str:
        """Return mac address.

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :rtype: str
        """
        sys_info = self.sys_info

        if "mac" in sys_info:
            return str(sys_info["mac"])
        elif "mic_mac" in sys_info:
            return ":".join(
                format(s, "02x") for s in bytes.fromhex(sys_info["mic_mac"])
            )

        raise SmartDeviceException(
            "Unknown mac, please submit a bug report with sys_info output."
        )

    async def set_mac(self, mac):
        """Set the mac address.

        :param str mac: mac in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_mac_addr", {"mac": mac})
        await self.update()

    @requires_update
    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings.

        :returns: current readings or False
        :rtype: dict, None
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        return EmeterStatus(await self._query_helper(self.emeter_type, "get_realtime"))

    @requires_update
    async def get_emeter_daily(
        self, year: int = None, month: int = None, kwh: bool = True
    ) -> Dict:
        """Retrieve daily statistics for a given month.

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistics (default: this
                      month)
        :param kwh: return usage in kWh (default: True)
        :return: mapping of day of month to value
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        response = await self._query_helper(
            self.emeter_type, "get_daystat", {"month": month, "year": year}
        )
        response = [EmeterStatus(**x) for x in response["day_list"]]

        key = "energy_wh"
        if kwh:
            key = "energy"

        data = {entry["day"]: entry[key] for entry in response}

        return data

    @requires_update
    async def get_emeter_monthly(self, year: int = None, kwh: bool = True) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        if year is None:
            year = datetime.now().year

        response = await self._query_helper(
            self.emeter_type, "get_monthstat", {"year": year}
        )
        response = [EmeterStatus(**x) for x in response["month_list"]]

        key = "energy_wh"
        if kwh:
            key = "energy"

        return {entry["month"]: entry[key] for entry in response}

    @requires_update
    async def erase_emeter_stats(self):
        """Erase energy meter statistics.

        :return: True if statistics were deleted
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        await self._query_helper(self.emeter_type, "erase_emeter_stat", None)
        await self.update()

    @requires_update
    async def current_consumption(self) -> float:
        """Get the current power consumption in Watt.

        :return: the current power consumption in Watts.
        :raises SmartDeviceException: on error
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        response = EmeterStatus(await self.get_emeter_realtime())
        return response["power"]

    async def reboot(self, delay=1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.

        :param delay: Delay the reboot for `delay` seconds.
        :return: None
        """
        await self._query_helper("system", "reboot", {"delay": delay})

    async def turn_off(self) -> None:
        """Turn off the device."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def is_off(self) -> bool:
        """Return True if device is off.

        :return: True if device is off, False otherwise.
        :rtype: bool
        """
        return not self.is_on

    async def turn_on(self) -> None:
        """Turn device on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return if the device is on.

        :return: True if the device is on, False otherwise.
        :rtype: bool
        :return:
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def on_since(self) -> Optional[datetime]:
        """Return pretty-printed on-time, if available.

        Returns None if the device is turned off or does not report it.
        """
        if "on_time" not in self.sys_info:
            return None

        if self.is_off:
            return None

        on_time = self.sys_info["on_time"]

        return datetime.now() - timedelta(seconds=on_time)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return device-type specific, end-user friendly state information.

        :return: dict with state information.
        :rtype: dict
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def device_id(self) -> str:
        """Return unique ID for the device.

        This is the MAC address of the device.
        """
        return self.mac

    async def wifi_scan(self) -> List[WifiNetwork]:
        """Scan for available wifi networks."""
        info = await self._query_helper("netif", "get_scaninfo", {"refresh": 1})
        if "ap_list" not in info:
            raise SmartDeviceException("Invalid response for wifi scan: %s" % info)

        return [WifiNetwork(**x) for x in info["ap_list"]]

    async def wifi_join(self, ssid, password, keytype=3):
        """Join the given wifi network.

        If joining the network fails, the device will return to AP mode after a while.
        """
        payload = {"ssid": ssid, "password": password, "key_type": keytype}
        return await self._query_helper("netif", "set_stainfo", payload)

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return self._device_type

    @property
    def is_bulb(self) -> bool:
        """Return True if the device is a bulb."""
        return self._device_type == DeviceType.Bulb

    @property
    def is_plug(self) -> bool:
        """Return True if the device is a plug."""
        return self._device_type == DeviceType.Plug

    @property
    def is_strip(self) -> bool:
        """Return True if the device is a strip."""
        return self._device_type == DeviceType.Strip

    @property
    def is_dimmer(self) -> bool:
        """Return True if the device is a dimmer."""
        return self._device_type == DeviceType.Dimmer

    @property
    def is_dimmable(self) -> bool:
        """Return  True if the device is dimmable."""
        return False

    @property
    def is_variable_color_temp(self) -> bool:
        """Return True if the device supports color temperature."""
        return False

    def __repr__(self):
        return "<{} model {} at {} ({}), is_on: {} - dev specific: {}>".format(
            self.__class__.__name__,
            self.model,
            self.host,
            self.alias,
            self.is_on,
            self.state_information,
        )
