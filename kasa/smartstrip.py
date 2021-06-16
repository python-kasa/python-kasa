"""Module for multi-socket devices (HS300, HS107, KP303, ..)."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Dict, Optional

from kasa.smartdevice import (
    DeviceType,
    SmartDevice,
    SmartDeviceException,
    requires_update,
)
from kasa.smartplug import SmartPlug

_LOGGER = logging.getLogger(__name__)


class SmartStrip(SmartDevice):
    """Representation of a TP-Link Smart Power Strip.

    A strip consists of the parent device and its children.
    All methods of the parent act on all children, while the child devices
    share the common API with the :class:`SmartPlug` class.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`s,
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

    def __init__(self, host: str) -> None:
        super().__init__(host=host)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return if any of the outlets are on."""
        for plug in self.children:
            is_on = plug.is_on
            if is_on:
                return True
        return False

    async def update(self):
        """Update some of the attributes.

        Needed for methods that are decorated with `requires_update`.
        """
        await super().update()

        # Initialize the child devices during the first update.
        if not self.children:
            children = self.sys_info["children"]
            _LOGGER.debug("Initializing %s child sockets", len(children))
            for child in children:
                self.children.append(
                    SmartStripPlug(self.host, parent=self, child_id=child["id"])
                )

    async def turn_on(self, **kwargs):
        """Turn the strip on."""
        await self._query_helper("system", "set_relay_state", {"state": 1})
        await self.update()

    async def turn_off(self, **kwargs):
        """Turn the strip off."""
        await self._query_helper("system", "set_relay_state", {"state": 0})
        await self.update()

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
        await self.update()

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
        consumption = sum(await plug.current_consumption() for plug in self.children)

        return consumption

    async def set_alias(self, alias: str) -> None:
        """Set the alias for the strip.

        :param alias: new alias
        """
        return await super().set_alias(alias)

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
        """
        emeter_daily: DefaultDict[int, float] = defaultdict(lambda: 0.0)
        for plug in self.children:
            plug_emeter_daily = await plug.get_emeter_daily(
                year=year, month=month, kwh=kwh
            )
            for day, value in plug_emeter_daily.items():
                emeter_daily[day] += value
        return emeter_daily

    @requires_update
    async def get_emeter_monthly(self, year: int = None, kwh: bool = True) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        """
        emeter_monthly: DefaultDict[int, float] = defaultdict(lambda: 0.0)
        for plug in self.children:
            plug_emeter_monthly = await plug.get_emeter_monthly(year=year, kwh=kwh)
            for month, value in plug_emeter_monthly:
                emeter_monthly[month] += value

        return emeter_monthly

    @requires_update
    async def erase_emeter_stats(self):
        """Erase energy meter statistics for all plugs."""
        for plug in self.children:
            await plug.erase_emeter_stats()


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
        self._sys_info = parent._sys_info

    async def update(self):
        """Override the update to no-op and inform the user."""
        _LOGGER.warning(
            "You called update() on a child device, which has no effect."
            "Call update() on the parent device instead."
        )
        return

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
    def has_emeter(self) -> bool:
        """Children have no emeter to my knowledge."""
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

        return datetime.now() - timedelta(seconds=on_time)

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
