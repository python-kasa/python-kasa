"""Module for multi-socket devices (HS300, HS107).

.. todo:: describe how this interfaces with single plugs.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, DefaultDict, Dict, List, Optional

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

    Usage example when used as library:
    ```python
    p = SmartStrip("192.168.1.105")

    # query the state of the strip
    await p.update()
    print(p.is_on)

    # change state of all outlets
    await p.turn_on()
    await p.turn_off()

    # individual outlets are accessible through plugs variable
    for plug in p.plugs:
        print(f"{p}: {p.is_on}")

    # change state of a single outlet
    await p.plugs[0].turn_on()
    ```

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    def __init__(self, host: str) -> None:
        super().__init__(host=host)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip
        self.plugs: List[SmartStripPlug] = []

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return if any of the outlets are on."""
        for plug in self.plugs:
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
        if not self.plugs:
            children = self.sys_info["children"]
            _LOGGER.debug("Initializing %s child sockets", len(children))
            for child in children:
                self.plugs.append(
                    SmartStripPlug(self.host, parent=self, child_id=child["id"])
                )

    async def turn_on(self):
        """Turn the strip on.

        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_relay_state", {"state": 1})
        await self.update()

    async def turn_off(self):
        """Turn the strip off.

        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_relay_state", {"state": 0})
        await self.update()

    def get_plug_by_name(self, name: str) -> "SmartStripPlug":
        """Return child plug for given name."""
        for p in self.plugs:
            if p.alias == name:
                return p

        raise SmartDeviceException(f"Device has no child with {name}")

    def get_plug_by_index(self, index: int) -> "SmartStripPlug":
        """Return child plug for given index."""
        if index + 1 > len(self.plugs) or index < 0:
            raise SmartDeviceException(
                f"Invalid index {index}, device has {len(self.plugs)} plugs"
            )
        return self.plugs[index]

    @property  # type: ignore
    @requires_update
    def on_since(self) -> Optional[datetime]:
        """Return the maximum on-time of all outlets."""
        if self.is_off:
            return None

        return max(plug.on_since for plug in self.plugs if plug.on_since is not None)

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led.

        :return: True if led is on, False otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(1 - sys_info["led_off"])

    async def set_led(self, state: bool):
        """Set the state of the led (night mode).

        :param bool state: True to set led on, False to set led off
        :raises SmartDeviceException: on error
        """
        await self._query_helper("system", "set_led_off", {"off": int(not state)})
        await self.update()

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        :rtype: dict
        """
        return {
            "LED state": self.led,
            "Childs count": len(self.plugs),
            "On since": self.on_since,
        }

    async def current_consumption(self) -> float:
        """Get the current power consumption in watts.

        :return: the current power consumption in watts.
        :rtype: float
        :raises SmartDeviceException: on error
        """
        consumption = sum([await plug.current_consumption() for plug in self.plugs])

        return consumption

    async def get_icon(self) -> Dict:
        """Icon for the device.

        Overriden to keep the API, as the SmartStrip and children do not
        have icons, we just return dummy strings.
        """
        return {"icon": "SMARTSTRIP-DUMMY", "hash": "SMARTSTRIP-DUMMY"}

    async def set_alias(self, alias: str) -> None:
        """Set the alias for the strip.

        :param alias: new alias
        :raises SmartDeviceException: on error
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
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        emeter_daily: DefaultDict[int, float] = defaultdict(lambda: 0.0)
        for plug in self.plugs:
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
        :return: dict: mapping of month to value
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        emeter_monthly: DefaultDict[int, float] = defaultdict(lambda: 0.0)
        for plug in self.plugs:
            plug_emeter_monthly = await plug.get_emeter_monthly(year=year, kwh=kwh)
            for month, value in plug_emeter_monthly:
                emeter_monthly[month] += value

        return emeter_monthly

    @requires_update
    async def erase_emeter_stats(self):
        """Erase energy meter statistics for all plugs.

        :raises SmartDeviceException: on error
        """
        for plug in self.plugs:
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
        """Return whether device is on.

        :return: True if device is on, False otherwise
        """
        info = self._get_child_info()
        return info["state"]

    @property  # type: ignore
    @requires_update
    def led(self) -> bool:
        """Return the state of the led.

        This is always false for subdevices.

        :return: True if led is on, False otherwise
        :rtype: bool
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
        """Return device name (alias).

        :return: Device name aka alias.
        :rtype: str
        """
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
        """Return pretty-printed on-time.

        :return: datetime for on since
        :rtype: datetime
        """
        if self.is_off:
            return None

        info = self._get_child_info()
        on_time = info["on_time"]

        return datetime.now() - timedelta(seconds=on_time)

    @property  # type: ignore
    @requires_update
    def model(self) -> str:
        """Return device model for a child socket.

        :return: device model
        :rtype: str
        :raises SmartDeviceException: on error
        """
        sys_info = self.parent.sys_info
        return f"Socket for {sys_info['model']}"

    def _get_child_info(self) -> Dict:
        """Return the subdevice information for this device.

        :raises SmartDeviceException: if the information is not found.
        """
        for plug in self.parent.sys_info["children"]:
            if plug["id"] == self.child_id:
                return plug
        raise SmartDeviceException(f"Unable to find children {self.child_id}")
