"""Module for multi-socket devices (HS300, HS107).

.. todo:: describe how this interfaces with single plugs.
"""
import datetime
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, List

from .protocol import TPLinkSmartHomeProtocol
from .smartplug import DeviceType, SmartPlug

_LOGGER = logging.getLogger(__name__)


class SmartStrip(SmartPlug):
    """Representation of a TP-Link Smart Power Strip.

    Usage example when used as library:
    p = SmartStrip("192.168.1.105")

    # query the state of the strip
    print(p.is_on)

    # change state of all outlets
    p.turn_on()
    p.turn_off()

    # individual outlets are accessible through plugs variable
    for plug in p.plugs:
        print("%s: %s" % (p, p.is_on))

    # change state of a single outlet
    p.plugs[0].turn_on()

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    def __init__(
        self, host: str, protocol: TPLinkSmartHomeProtocol = None, cache_ttl: int = 3
    ) -> None:
        SmartPlug.__init__(self, host=host, protocol=protocol, cache_ttl=cache_ttl)
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip
        self.plugs: List[SmartPlug] = []
        children = self.sys_info["children"]
        self.num_children = len(children)
        for plug in range(self.num_children):
            self.plugs.append(
                SmartPlug(
                    host, protocol, context=children[plug]["id"], cache_ttl=cache_ttl
                )
            )

    @property
    def is_on(self) -> bool:
        """Return if any of the outlets are on."""
        return any(plug.is_on for plug in self.plugs)

    def turn_on(self):
        """Turn the strip on.

        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 1})

    def turn_off(self):
        """Turn the strip off.

        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 0})

    @property
    def on_since(self) -> datetime.datetime:
        """Return the maximum on-time of all outlets."""
        return max(plug.on_since for plug in self.plugs)

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        :rtype: dict
        """
        state: Dict[str, Any] = {"LED state": self.led}
        for plug in self.plugs:
            if plug.is_on:
                state["Plug %s on since" % str(plug)] = plug.on_since

        return state

    def current_consumption(self) -> float:
        """Get the current power consumption in watts.

        :return: the current power consumption in watts.
        :rtype: float
        :raises SmartDeviceException: on error
        """
        consumption = sum(plug.current_consumption() for plug in self.plugs)

        return consumption

    @property  # type: ignore # required to avoid mypy error on non-implemented setter
    def icon(self) -> Dict:
        """Icon for the device.

        Overriden to keep the API, as the SmartStrip and children do not
        have icons, we just return dummy strings.
        """
        return {"icon": "SMARTSTRIP-DUMMY", "hash": "SMARTSTRIP-DUMMY"}

    def set_alias(self, alias: str) -> None:
        """Set the alias for the strip.

        :param alias: new alias
        :raises SmartDeviceException: on error
        """
        return super().set_alias(alias)

    def get_emeter_daily(
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
            for day, value in plug.get_emeter_daily(
                year=year, month=month, kwh=kwh
            ).items():
                emeter_daily[day] += value
        return emeter_daily

    def get_emeter_monthly(self, year: int = None, kwh: bool = True) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
        :rtype: dict
        :raises SmartDeviceException: on error
        """
        emeter_monthly: DefaultDict[int, float] = defaultdict(lambda: 0.0)
        for plug in self.plugs:
            for month, value in plug.get_emeter_monthly(year=year, kwh=kwh):
                emeter_monthly[month] += value
        return emeter_monthly

    def erase_emeter_stats(self):
        """Erase energy meter statistics for all plugs.

        :raises SmartDeviceException: on error
        """
        for plug in self.plugs:
            plug.erase_emeter_stats()
