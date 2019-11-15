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
import asyncio
import functools
import inspect
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

from pyHS100.protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    """Device type enum."""

    Plug = 1
    Bulb = 2
    Strip = 3
    Unknown = -1


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
                return super().__getitem__(item[: item.find("_")]) * 10 ** 3
            else:  # downscale
                for i in super().keys():
                    if i.startswith(item):
                        return self.__getitem__(i) / 10 ** 3

                raise SmartDeviceException("Unable to find a value for '%s'" % item)


class SmartDevice:
    """Base class for all supported device types."""

    STATE_ON = "ON"
    STATE_OFF = "OFF"

    def __init__(
        self,
        host: str,
        protocol: Optional[TPLinkSmartHomeProtocol] = None,
        context: str = None,
        cache_ttl: int = 3,
        *,
        ioloop=None,
    ) -> None:
        """Create a new SmartDevice instance.

        :param str host: host name or ip address on which the device listens
        :param context: optional child ID for context in a parent device
        """
        self.host = host
        if protocol is None:  # pragma: no cover
            protocol = TPLinkSmartHomeProtocol()
        self.protocol = protocol
        self.emeter_type = "emeter"
        self.context = context
        self.num_children = 0
        self.cache_ttl = timedelta(seconds=cache_ttl)
        _LOGGER.debug(
            "Initializing %s using context %s and cache ttl %s",
            self.host,
            self.context,
            self.cache_ttl,
        )
        self.cache = defaultdict(lambda: defaultdict(lambda: None))  # type: ignore
        self._device_type = DeviceType.Unknown
        self.ioloop = ioloop or asyncio.get_event_loop()
        self.sync = SyncSmartDevice(self, ioloop=self.ioloop)

    def _result_from_cache(self, target, cmd) -> Optional[Dict]:
        """Return query result from cache if still fresh.

        Only results from commands starting with `get_` are considered cacheable.

        :param target: Target system
        :param cmd: Command
        :rtype: query result or None if expired.
        """
        _LOGGER.debug("Checking cache for %s %s", target, cmd)
        if cmd not in self.cache[target]:
            return None

        cached = self.cache[target][cmd]
        if cached and cached["last_updated"] is not None:
            if cached[
                "last_updated"
            ] + self.cache_ttl > datetime.utcnow() and cmd.startswith("get_"):
                _LOGGER.debug("Got cached %s %s", target, cmd)
                return self.cache[target][cmd]
            else:
                _LOGGER.debug("Invalidating the cache for %s cmd %s", target, cmd)
                for cache_entry in self.cache[target].values():
                    cache_entry["last_updated"] = datetime.utcfromtimestamp(0)
        return None

    def _insert_to_cache(self, target: str, cmd: str, response: Dict) -> None:
        """Add response for a given command to the cache.

        :param target: Target system
        :param cmd: Command
        :param response: Response to be cached
        """
        self.cache[target][cmd] = response.copy()
        self.cache[target][cmd]["last_updated"] = datetime.utcnow()

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None
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
        if self.context is not None:
            request = {"context": {"child_ids": [self.context]}, target: {cmd: arg}}

        try:
            response = self._result_from_cache(target, cmd)
            if response is None:
                _LOGGER.debug("Got no result from cache, querying the device.")
                response = await self.protocol.query(host=self.host, request=request)
                self._insert_to_cache(target, cmd, response)
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

    async def get_has_emeter(self) -> bool:
        """Return if device has an energy meter.

        :return: True if energey meter is available
                 False if energymeter is missing
        """
        raise NotImplementedError()

    async def get_sys_info(self) -> Dict[str, Any]:
        """Retrieve system information.

        :return: sysinfo
        :rtype dict
        :raises SmartDeviceException: on error
        """
        return await self._query_helper("system", "get_sysinfo")

    async def get_model(self) -> str:
        """Return device model.

        :return: device model
        :rtype: str
        :raises SmartDeviceException: on error
        """
        sys_info = await self.get_sys_info()
        return str(sys_info["model"])

    async def get_alias(self) -> str:
        """Return device name (alias).

        :return: Device name aka alias.
        :rtype: str
        """
        sys_info = await self.get_sys_info()
        return str(sys_info["alias"])

    async def set_alias(self, alias: str) -> None:
        """Set the device name (alias).

        :param alias: New alias (name)
        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_dev_alias", {"alias": alias})

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

    async def get_hw_info(self) -> Dict:
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
        sys_info = await self.get_sys_info()
        return {key: sys_info[key] for key in keys if key in sys_info}

    async def get_location(self) -> Dict:
        """Return geographical location.

        :return: latitude and longitude
        :rtype: dict
        """
        info = await self.get_sys_info()
        loc = {"latitude": None, "longitude": None}

        if "latitude" in info and "longitude" in info:
            loc["latitude"] = info["latitude"]
            loc["longitude"] = info["longitude"]
        elif "latitude_i" in info and "longitude_i" in info:
            loc["latitude"] = info["latitude_i"]
            loc["longitude"] = info["longitude_i"]
        else:
            _LOGGER.warning("Unsupported device location.")

        return loc

    async def get_rssi(self) -> Optional[int]:
        """Return WiFi signal strenth (rssi).

        :return: rssi
        :rtype: int
        """
        sys_info = await self.get_sys_info()
        if "rssi" in sys_info:
            return int(sys_info["rssi"])
        return None

    async def get_mac(self) -> str:
        """Return mac address.

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        :rtype: str
        """
        sys_info = await self.get_sys_info()

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

    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings.

        :returns: current readings or False
        :rtype: dict, None
        :raises SmartDeviceException: on error
        """
        if not await self.get_has_emeter():
            raise SmartDeviceException("Device has no emeter")

        return EmeterStatus(await self._query_helper(self.emeter_type, "get_realtime"))

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
        if not await self.get_has_emeter():
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

    async def get_emeter_monthly(self, year: int = None, kwh: bool = True) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        if not await self.get_has_emeter():
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

    async def erase_emeter_stats(self) -> bool:
        """Erase energy meter statistics.

        :return: True if statistics were deleted
        :raises SmartDeviceException: on error
        """
        if not await self.get_has_emeter():
            raise SmartDeviceException("Device has no emeter")

        await self._query_helper(self.emeter_type, "erase_emeter_stat", None)

    async def current_consumption(self) -> Optional[float]:
        """Get the current power consumption in Watt.

        :return: the current power consumption in Watts.
        :raises SmartDeviceException: on error
        """
        if not await self.get_has_emeter():
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

    async def is_off(self) -> bool:
        """Return True if device is off.

        :return: True if device is off, False otherwise.
        :rtype: bool
        """
        return not await self.is_on()

    async def turn_on(self) -> None:
        """Turn device on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    async def is_on(self) -> bool:
        """Return if the device is on.

        :return: True if the device is on, False otherwise.
        :rtype: bool
        :return:
        """
        raise NotImplementedError("Device subclass needs to implement this.")

    async def get_state_information(self) -> Dict[str, Any]:
        """Return device-type specific, end-user friendly state information.

        :return: dict with state information.
        :rtype: dict
        """
        raise NotImplementedError("Device subclass needs to implement this.")

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

    async def is_dimmable(self):
        """Return  True if the device is dimmable."""
        return False

    @property
    def is_variable_color_temp(self) -> bool:
        """Return True if the device supports color temperature."""
        return False

    def __repr__(self):
        return "<{} model {} at {} ({}), is_on: {} - dev specific: {}>".format(
            self.__class__.__name__,
            self.sync.get_model(),
            self.host,
            self.sync.get_alias(),
            self.sync.is_on(),
            self.sync.get_state_information(),
        )


class SyncSmartDevice:
    """A synchronous SmartDevice speaker class.
    This has the same methods as `SyncSmartDevice`, however, it wraps all async
    methods and call them in a blocking way.

    Taken from https://github.com/basnijholt/media_player.kef/
    """

    def __init__(self, async_device, ioloop):
        self.async_device = async_device
        self.ioloop = ioloop

    def __getattr__(self, attr):
        method = getattr(self.async_device, attr)
        if method is None:
            raise AttributeError(f"'SyncSmartDevice' object has no attribute '{attr}.'")
        if inspect.iscoroutinefunction(method):

            @functools.wraps(method)
            def wrapped(*args, **kwargs):
                return self.ioloop.run_until_complete(method(*args, **kwargs))

            return wrapped
        else:
            return method
