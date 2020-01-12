"""Module for multi-socket devices (HS300, HS107).

.. todo:: describe how this interfaces with single plugs.
"""
import datetime
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List

from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartdevice import DeviceType, requires_update
from kasa.smartplug import SmartPlug

_LOGGER = logging.getLogger(__name__)


class SmartStrip(SmartPlug):
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

    def __init__(
        self,
        host: str,
        protocol: TPLinkSmartHomeProtocol = None,
        cache_ttl: int = 3,
        ioloop=None,
    ) -> None:
        SmartPlug.__init__(self, host=host, protocol=protocol, cache_ttl=cache_ttl)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip
        self.plugs: List[SmartPlug] = []

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
            self.num_children = len(children)
            for child in children:
                self.plugs.append(
                    SmartPlug(
                        self.host,
                        self.protocol,
                        child_id=child["id"],
                        cache_ttl=self.cache_ttl.total_seconds(),
                        ioloop=self.ioloop,
                    )
                )

        for plug in self.plugs:
            await plug.update()

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

    @property  # type: ignore
    @requires_update
    def on_since(self) -> datetime.datetime:
        """Return the maximum on-time of all outlets."""
        return max(plug.on_since for plug in self.plugs)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        :rtype: dict
        """
        state: Dict[str, Any] = {"LED state": self.led}
        for plug in self.plugs:
            if plug.is_on:
                state["Plug %s on since" % str(plug)] = self.on_since

        return state

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
