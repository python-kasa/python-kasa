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

from .exceptions import SmartDeviceException
from .protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class DeviceType(Enum):
    """Device type enum."""

    Plug = 1
    Bulb = 2
    Strip = 3
    Dimmer = 4
    LightStrip = 5
    Unknown = -1


@dataclass
class WifiNetwork:
    """Wifi network container."""

    ssid: str
    key_type: int
    # These are available only on softaponboarding
    cipher_type: Optional[int] = None
    bssid: Optional[str] = None
    channel: Optional[int] = None
    rssi: Optional[int] = None


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

                _LOGGER.debug(f"Unable to find value for '{item}'")
                return None


def requires_update(f):
    """Indicate that `update` should be called before accessing this method."""  # noqa: D202
    if inspect.iscoroutinefunction(f):

        @functools.wraps(f)
        async def wrapped(*args, **kwargs):
            self = args[0]
            if self._last_update is None:
                raise SmartDeviceException(
                    "You need to await update() to access the data"
                )
            return await f(*args, **kwargs)

    else:

        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            self = args[0]
            if self._last_update is None:
                raise SmartDeviceException(
                    "You need to await update() to access the data"
                )
            return f(*args, **kwargs)

    f.requires_update = True
    return wrapped


class SmartDevice:
    """Base class for all supported device types.

    You don't usually want to construct this class which implements the shared common interfaces.
    The recommended way is to either use the discovery functionality, or construct one of the subclasses:

    * :class:`SmartPlug`
    * :class:`SmartBulb`
    * :class:`SmartStrip`
    * :class:`SmartDimmer`
    * :class:`SmartLightStrip`

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await update() separately.

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> dev = SmartDevice("127.0.0.1")
        >>> asyncio.run(dev.update())

        All devices provide several informational properties:

        >>> dev.alias
        Kitchen
        >>> dev.model
        HS110(EU)
        >>> dev.rssi
        -71
        >>> dev.mac
        50:C7:BF:01:F8:CD

        Some information can also be changed programatically:

        >>> asyncio.run(dev.set_alias("new alias"))
        >>> asyncio.run(dev.set_mac("01:23:45:67:89:ab"))
        >>> asyncio.run(dev.update())
        >>> dev.alias
        new alias
        >>> dev.mac
        01:23:45:67:89:ab

        When initialized using discovery or using a subclass, you can check the type of the device:

        >>> dev.is_bulb
        False
        >>> dev.is_strip
        False
        >>> dev.is_plug
        True

        You can also get the hardware and software as a dict, or access the full device response:

        >>> dev.hw_info
        {'sw_ver': '1.2.5 Build 171213 Rel.101523',
         'hw_ver': '1.0',
         'mac': '01:23:45:67:89:ab',
         'type': 'IOT.SMARTPLUGSWITCH',
         'hwId': '45E29DA8382494D2E82688B52A0B2EB5',
         'fwId': '00000000000000000000000000000000',
         'oemId': '3D341ECE302C0642C99E31CE2430544B',
         'dev_name': 'Wi-Fi Smart Plug With Energy Monitoring'}
        >>> dev.sys_info

        All devices can be turned on and off:

        >>> asyncio.run(dev.turn_off())
        >>> asyncio.run(dev.turn_on())
        >>> asyncio.run(dev.update())
        >>> dev.is_on
        True

        Some devices provide energy consumption meter, and regular update will already fetch some information:

        >>> dev.has_emeter
        True
        >>> dev.emeter_realtime
        {'current': 0.015342, 'err_code': 0, 'power': 0.983971, 'total': 32.448, 'voltage': 235.595234}
        >>> dev.emeter_today
        >>> dev.emeter_this_month

        You can also query the historical data (note that these needs to be awaited), keyed with month/day:

        >>> asyncio.run(dev.get_emeter_monthly(year=2016))
        {11: 1.089, 12: 1.582}
        >>> asyncio.run(dev.get_emeter_daily(year=2016, month=11))
        {24: 0.026, 25: 0.109}

    """

    def __init__(self, host: str) -> None:
        """Create a new SmartDevice instance.

        :param str host: host name or ip address on which the device listens
        """
        self.host = host

        self.protocol = TPLinkSmartHomeProtocol()
        self.emeter_type = "emeter"
        _LOGGER.debug("Initializing %s of type %s", self.host, type(self))
        self._device_type = DeviceType.Unknown
        # TODO: typing Any is just as using Optional[Dict] would require separate checks in
        #       accessors. the @updated_required decorator does not ensure mypy that these
        #       are not accessed incorrectly.
        self._last_update: Any = None
        self._sys_info: Any = None  # TODO: this is here to avoid changing tests

        self.children: List["SmartDevice"] = []

    def _create_request(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ):
        request: Dict[str, Any] = {target: {cmd: arg}}
        if child_ids is not None:
            request = {"context": {"child_ids": child_ids}, target: {cmd: arg}}

        return request

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        """Query device, return results or raise an exception.

        :param target: Target system {system, time, emeter, ..}
        :param cmd: Command to execute
        :param arg: payload dict to be send to the device
        :param child_ids: ids of child devices
        :return: Unwrapped result for the call.
        """
        request = self._create_request(target, cmd, arg, child_ids)

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
        """Return True if device has an energy meter."""
        sys_info = self.sys_info
        features = sys_info["feature"].split(":")
        return "ENE" in features

    async def get_sys_info(self) -> Dict[str, Any]:
        """Retrieve system information."""
        return await self._query_helper("system", "get_sysinfo")

    async def update(self):
        """Update some of the attributes.

        Needed for methods that are decorated with `requires_update`.
        """
        req = {}
        req.update(self._create_request("system", "get_sysinfo"))

        # Check for emeter if we were never updated, or if the device has emeter
        if self._last_update is None or self.has_emeter:
            req.update(self._create_emeter_request())
        self._last_update = await self.protocol.query(self.host, req)
        # TODO: keep accessible for tests
        self._sys_info = self._last_update["system"]["get_sysinfo"]

    def update_from_discover_info(self, info):
        """Update state from info from the discover call."""
        self._last_update = info
        self._sys_info = info["system"]["get_sysinfo"]

    @property  # type: ignore
    @requires_update
    def sys_info(self) -> Dict[str, Any]:
        """Return system information."""
        return self._sys_info  # type: ignore

    @property  # type: ignore
    @requires_update
    def model(self) -> str:
        """Return device model."""
        sys_info = self.sys_info
        return str(sys_info["model"])

    @property  # type: ignore
    @requires_update
    def alias(self) -> str:
        """Return device name (alias)."""
        sys_info = self.sys_info
        return str(sys_info["alias"])

    async def set_alias(self, alias: str) -> None:
        """Set the device name (alias)."""
        return await self._query_helper("system", "set_dev_alias", {"alias": alias})

    async def get_time(self) -> Optional[datetime]:
        """Return current time from the device, if available."""
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

    async def get_timezone(self) -> Dict:
        """Return timezone information."""
        return await self._query_helper("time", "get_timezone")

    @property  # type: ignore
    @requires_update
    def hw_info(self) -> Dict:
        """Return hardware information.

        This returns just a selection of sysinfo keys that are related to hardware.
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
        """Return geographical location."""
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
        """Return WiFi signal strenth (rssi)."""
        sys_info = self.sys_info
        if "rssi" in sys_info:
            return int(sys_info["rssi"])
        return None

    @property  # type: ignore
    @requires_update
    def mac(self) -> str:
        """Return mac address.

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        """
        sys_info = self.sys_info

        mac = sys_info.get("mac", sys_info.get("mic_mac"))
        if not mac:
            raise SmartDeviceException(
                "Unknown mac, please submit a bug report with sys_info output."
            )

        if ":" not in mac:
            mac = ":".join(format(s, "02x") for s in bytes.fromhex(mac))

        return mac

    async def set_mac(self, mac):
        """Set the mac address.

        :param str mac: mac in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        """
        return await self._query_helper("system", "set_mac_addr", {"mac": mac})

    @property  # type: ignore
    @requires_update
    def emeter_realtime(self) -> EmeterStatus:
        """Return current energy readings."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        return EmeterStatus(self._last_update[self.emeter_type]["get_realtime"])

    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        return EmeterStatus(await self._query_helper(self.emeter_type, "get_realtime"))

    def _create_emeter_request(self, year: int = None, month: int = None):
        """Create a Internal method for building a request for all emeter statistics at once."""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        import collections.abc

        def update(d, u):
            """Update dict recursively."""
            for k, v in u.items():
                if isinstance(v, collections.abc.Mapping):
                    d[k] = update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d

        req: Dict[str, Any] = {}
        update(req, self._create_request(self.emeter_type, "get_realtime"))
        update(
            req, self._create_request(self.emeter_type, "get_monthstat", {"year": year})
        )
        update(
            req,
            self._create_request(
                self.emeter_type, "get_daystat", {"month": month, "year": year}
            ),
        )

        return req

    @property  # type: ignore
    @requires_update
    def emeter_today(self) -> Optional[float]:
        """Return today's energy consumption in kWh."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        raw_data = self._last_update[self.emeter_type]["get_daystat"]["day_list"]
        data = self._emeter_convert_emeter_data(raw_data)
        today = datetime.now().day

        if today in data:
            return data[today]

        return None

    @property  # type: ignore
    @requires_update
    def emeter_this_month(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        raw_data = self._last_update[self.emeter_type]["get_monthstat"]["month_list"]
        data = self._emeter_convert_emeter_data(raw_data)
        current_month = datetime.now().month

        if current_month in data:
            return data[current_month]

        return None

    def _emeter_convert_emeter_data(self, data, kwh=True) -> Dict:
        """Return emeter information keyed with the day/month.."""
        response = [EmeterStatus(**x) for x in data]

        if not response:
            return {}

        energy_key = "energy_wh"
        if kwh:
            energy_key = "energy"

        entry_key = "month"
        if "day" in response[0]:
            entry_key = "day"

        data = {entry[entry_key]: entry[energy_key] for entry in response}

        return data

    async def get_emeter_daily(
        self, year: int = None, month: int = None, kwh: bool = True
    ) -> Dict:
        """Retrieve daily statistics for a given month.

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistics (default: this
                      month)
        :param kwh: return usage in kWh (default: True)
        :return: mapping of day of month to value
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

        return self._emeter_convert_emeter_data(response["day_list"], kwh)

    @requires_update
    async def get_emeter_monthly(self, year: int = None, kwh: bool = True) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
        """
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        if year is None:
            year = datetime.now().year

        response = await self._query_helper(
            self.emeter_type, "get_monthstat", {"year": year}
        )

        return self._emeter_convert_emeter_data(response["month_list"], kwh)

    @requires_update
    async def erase_emeter_stats(self) -> Dict:
        """Erase energy meter statistics."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        return await self._query_helper(self.emeter_type, "erase_emeter_stat", None)

    @requires_update
    async def current_consumption(self) -> float:
        """Get the current power consumption in Watt."""
        if not self.has_emeter:
            raise SmartDeviceException("Device has no emeter")

        response = EmeterStatus(await self.get_emeter_realtime())
        return response["power"]

    async def reboot(self, delay: int = 1) -> None:
        """Reboot the device.

        Note that giving a delay of zero causes this to block,
        as the device reboots immediately without responding to the call.
        """
        await self._query_helper("system", "reboot", {"delay": delay})

    async def turn_off(self, **kwargs) -> Dict:
        """Turn off the device."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def is_off(self) -> bool:
        """Return True if device is off."""
        return not self.is_on

    async def turn_on(self, **kwargs) -> Dict:
        """Turn device on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return True if the device is on."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def on_since(self) -> Optional[datetime]:
        """Return pretty-printed on-time, or None if not available."""
        if "on_time" not in self.sys_info:
            return None

        if self.is_off:
            return None

        on_time = self.sys_info["on_time"]

        return datetime.now() - timedelta(seconds=on_time)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return device-type specific, end-user friendly state information."""
        raise NotImplementedError("Device subclass needs to implement this.")

    @property  # type: ignore
    @requires_update
    def device_id(self) -> str:
        """Return unique ID for the device.

        This is the MAC address of the device.
        """
        return self.mac

    async def wifi_scan(self) -> List[WifiNetwork]:  # noqa: D202
        """Scan for available wifi networks."""

        async def _scan(target):
            return await self._query_helper(target, "get_scaninfo", {"refresh": 1})

        try:
            info = await _scan("netif")
        except SmartDeviceException as ex:
            _LOGGER.debug(
                "Unable to scan using 'netif', retrying with 'softaponboarding': %s", ex
            )
            info = await _scan("smartlife.iot.common.softaponboarding")

        if "ap_list" not in info:
            raise SmartDeviceException("Invalid response for wifi scan: %s" % info)

        return [WifiNetwork(**x) for x in info["ap_list"]]

    async def wifi_join(self, ssid, password, keytype=3):  # noqa: D202
        """Join the given wifi network.

        If joining the network fails, the device will return to AP mode after a while.
        """

        async def _join(target, payload):
            return await self._query_helper(target, "set_stainfo", payload)

        payload = {"ssid": ssid, "password": password, "key_type": keytype}
        try:
            return await _join("netif", payload)
        except SmartDeviceException as ex:
            _LOGGER.debug(
                "Unable to join using 'netif', retrying with 'softaponboarding': %s", ex
            )
            return await _join("smartlife.iot.common.softaponboarding", payload)

    def get_plug_by_name(self, name: str) -> "SmartDevice":
        """Return child device for the given name."""
        for p in self.children:
            if p.alias == name:
                return p

        raise SmartDeviceException(f"Device has no child with {name}")

    def get_plug_by_index(self, index: int) -> "SmartDevice":
        """Return child device for the given index."""
        if index + 1 > len(self.children) or index < 0:
            raise SmartDeviceException(
                f"Invalid index {index}, device has {len(self.children)} plugs"
            )
        return self.children[index]

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return self._device_type

    @property
    def is_bulb(self) -> bool:
        """Return True if the device is a bulb."""
        return self._device_type == DeviceType.Bulb

    @property
    def is_light_strip(self) -> bool:
        """Return True if the device is a led strip."""
        return self._device_type == DeviceType.LightStrip

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

    @property
    def is_color(self) -> bool:
        """Return True if the device supports color changes."""
        return False

    def __repr__(self):
        if self._last_update is None:
            return f"<{self._device_type} at {self.host} - update() needed>"
        return f"<{self._device_type} model {self.model} at {self.host} ({self.alias}), is_on: {self.is_on} - dev specific: {self.state_information}>"
