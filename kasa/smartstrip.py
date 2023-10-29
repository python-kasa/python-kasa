"""Module for multi-socket devices (HS300, HS107, KP303, ..)."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Dict, Optional

from kasa.smartdevice import (
    DeviceType,
    EmeterStatus,
    SmartDevice,
    SmartDeviceException,
    merge,
    requires_update,
)
from kasa.smartplug import SmartPlug

from .credentials import Credentials
from .modules import Antitheft, Countdown, Emeter, Schedule, Time, Usage

_LOGGER = logging.getLogger(__name__)


def merge_sums(dicts):
    """Merge the sum of dicts."""
    total_dict: DefaultDict[int, float] = defaultdict(lambda: 0.0)
    for sum_dict in dicts:
        for day, value in sum_dict.items():
            total_dict[day] += value
    return total_dict


class SmartStrip(SmartDevice):
    r"""Representation of a TP-Link Smart Power Strip.

    A strip consists of the parent device and its children.
    All methods of the parent act on all children, while the child devices
    share the common API with the :class:`SmartPlug` class.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values,
    but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`\s,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> strip = SmartStrip("127.0.0.1")
        >>> asyncio.run(strip.update())
        >>> strip.alias
        TP-LINK_Power Strip_CF69

        All methods act on the whole strip:

        >>> for plug in strip.children:
        >>>    print(f"{plug.alias}: {plug.is_on}")
        Plug 1: True
        Plug 2: False
        Plug 3: False
        >>> strip.is_on
        True
        >>> asyncio.run(strip.turn_off())

        Accessing individual plugs can be done using the `children` property:

        >>> len(strip.children)
        3
        >>> for plug in strip.children:
        >>>    print(f"{plug.alias}: {plug.is_on}")
        Plug 1: False
        Plug 2: False
        Plug 3: False
        >>> asyncio.run(strip.children[1].turn_on())
        >>> asyncio.run(strip.update())
        >>> strip.is_on
        True

    For more examples, see the :class:`SmartDevice` class.
    """

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host=host, port=port, credentials=credentials, timeout=timeout)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip
        self.add_module("antitheft", Antitheft(self, "anti_theft"))
        self.add_module("schedule", Schedule(self, "schedule"))
        self.add_module("usage", Usage(self, "schedule"))
        self.add_module("time", Time(self, "time"))
        self.add_module("countdown", Countdown(self, "countdown"))
        self.add_module("emeter", Emeter(self, "emeter"))

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return if any of the outlets are on."""
        return any(plug.is_on for plug in self.children)

    async def update(self, update_children: bool = True):
        """Update some of the attributes.

        Needed for methods that are decorated with `requires_update`.
        """
        await super().update(update_children)

        # Initialize the child devices during the first update.
        if not self.children:
            children = self.sys_info["children"]
            _LOGGER.debug("Initializing %s child sockets", len(children))
            for child in children:
                self.children.append(
                    SmartStripPlug(self.host, parent=self, child_id=child["id"])
                )

        if update_children and self.has_emeter:
            for plug in self.children:
                await plug.update()

    async def turn_on(self, **kwargs):
        """Turn the strip on."""
        await self._query_helper("system", "set_relay_state", {"state": 1})

    async def turn_off(self, **kwargs):
        """Turn the strip off."""
        await self._query_helper("system", "set_relay_state", {"state": 0})

    @property  # type: ignore
    @requires_update
    def on_since(self) -> Optional[datetime]:
        """Return the maximum on-time of all outlets."""
        if self.is_off:
            return None

        return max(plug.on_since for plug in self.children if plug.on_since is not None)

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led."""
        sys_info = self.sys_info
        return bool(1 - sys_info["led_off"])

    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""
        await self._query_helper("system", "set_led_off", {"off": int(not state)})

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        """
        return {
            "LED state": self.led,
            "Childs count": len(self.children),
            "On since": self.on_since,
        }

    async def current_consumption(self) -> float:
        """Get the current power consumption in watts."""
        return sum([await plug.current_consumption() for plug in self.children])

    @requires_update
    async def get_emeter_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        emeter_rt = await self._async_get_emeter_sum("get_emeter_realtime", {})
        # Voltage is averaged since each read will result
        # in a slightly different voltage since they are not atomic
        emeter_rt["voltage_mv"] = int(emeter_rt["voltage_mv"] / len(self.children))
        return EmeterStatus(emeter_rt)

    @requires_update
    async def get_emeter_daily(
        self, year: Optional[int] = None, month: Optional[int] = None, kwh: bool = True
    ) -> Dict:
        """Retrieve daily statistics for a given month.

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistics (default: this
                      month)
        :param kwh: return usage in kWh (default: True)
        :return: mapping of day of month to value
        """
        return await self._async_get_emeter_sum(
            "get_emeter_daily", {"year": year, "month": month, "kwh": kwh}
        )

    @requires_update
    async def get_emeter_monthly(
        self, year: Optional[int] = None, kwh: bool = True
    ) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        """
        return await self._async_get_emeter_sum(
            "get_emeter_monthly", {"year": year, "kwh": kwh}
        )

    async def _async_get_emeter_sum(self, func: str, kwargs: Dict[str, Any]) -> Dict:
        """Retreive emeter stats for a time period from children."""
        self._verify_emeter()
        return merge_sums(
            [await getattr(plug, func)(**kwargs) for plug in self.children]
        )

    @requires_update
    async def erase_emeter_stats(self):
        """Erase energy meter statistics for all plugs."""
        for plug in self.children:
            await plug.erase_emeter_stats()

    @property  # type: ignore
    @requires_update
    def emeter_this_month(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        return sum(plug.emeter_this_month for plug in self.children)

    @property  # type: ignore
    @requires_update
    def emeter_today(self) -> Optional[float]:
        """Return this month's energy consumption in kWh."""
        return sum(plug.emeter_today for plug in self.children)

    @property  # type: ignore
    @requires_update
    def emeter_realtime(self) -> EmeterStatus:
        """Return current energy readings."""
        emeter = merge_sums([plug.emeter_realtime for plug in self.children])
        # Voltage is averaged since each read will result
        # in a slightly different voltage since they are not atomic
        emeter["voltage_mv"] = int(emeter["voltage_mv"] / len(self.children))
        return EmeterStatus(emeter)


class SmartStripPlug(SmartPlug):
    """Representation of a single socket in a power strip.

    This allows you to use the sockets as they were SmartPlug objects.
    Instead of calling an update on any of these, you should call an update
    on the parent device before accessing the properties.

    The plug inherits (most of) the system information from the parent.
    """

    def __init__(self, host: str, parent: "SmartStrip", child_id: str) -> None:
        super().__init__(host)

        self.parent = parent
        self.child_id = child_id
        self._last_update = parent._last_update
        self._set_sys_info(parent.sys_info)
        self._device_type = DeviceType.StripSocket
        self.modules = {}
        self.protocol = parent.protocol  # Must use the same connection as the parent
        self.add_module("time", Time(self, "time"))

    async def update(self, update_children: bool = True):
        """Query the device to update the data.

        Needed for properties that are decorated with `requires_update`.
        """
        await self._modular_update({})

    def _create_emeter_request(
        self, year: Optional[int] = None, month: Optional[int] = None
    ):
        """Create a request for requesting all emeter statistics at once."""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        req: Dict[str, Any] = {}

        merge(req, self._create_request("emeter", "get_realtime"))
        merge(req, self._create_request("emeter", "get_monthstat", {"year": year}))
        merge(
            req,
            self._create_request(
                "emeter", "get_daystat", {"month": month, "year": year}
            ),
        )

        return req

    def _create_request(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ):
        request: Dict[str, Any] = {
            "context": {"child_ids": [self.child_id]},
            target: {cmd: arg},
        }
        return request

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        """Override query helper to include the child_ids."""
        return await self.parent._query_helper(
            target, cmd, arg, child_ids=[self.child_id]
        )

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether device is on."""
        info = self._get_child_info()
        return bool(info["state"])

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led.

        This is always false for subdevices.
        """
        return False

    @property  # type: ignore
    @requires_update
    def device_id(self) -> str:
        """Return unique ID for the socket.

        This is a combination of MAC and child's ID.
        """
        return f"{self.mac}_{self.child_id}"

    @property  # type: ignore
    @requires_update
    def alias(self) -> str:
        """Return device name (alias)."""
        info = self._get_child_info()
        return info["alias"]

    @property  # type: ignore
    @requires_update
    def next_action(self) -> Dict:
        """Return next scheduled(?) action."""
        info = self._get_child_info()
        return info["next_action"]

    @property  # type: ignore
    @requires_update
    def on_since(self) -> Optional[datetime]:
        """Return on-time, if available."""
        if self.is_off:
            return None

        info = self._get_child_info()
        on_time = info["on_time"]

        return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)

    @property  # type: ignore
    @requires_update
    def model(self) -> str:
        """Return device model for a child socket."""
        sys_info = self.parent.sys_info
        return f"Socket for {sys_info['model']}"

    def _get_child_info(self) -> Dict:
        """Return the subdevice information for this device."""
        for plug in self.parent.sys_info["children"]:
            if plug["id"] == self.child_id:
                return plug

        raise SmartDeviceException(f"Unable to find children {self.child_id}")
