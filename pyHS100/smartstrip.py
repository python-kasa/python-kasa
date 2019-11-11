import asyncio
import datetime
import logging
from typing import Any, Dict, Optional, Union

from pyHS100.protocol import TPLinkSmartHomeProtocol
from pyHS100.smartdevice import DeviceType, EmeterStatus, SmartDeviceException
from pyHS100.smartplug import SmartPlug

_LOGGER = logging.getLogger(__name__)


class SmartStripException(SmartDeviceException):
    """SmartStripException gets raised for errors specific to the smart strip."""

    pass


class SmartStrip(SmartPlug):
    """Representation of a TP-Link Smart Power Strip.

    Usage example when used as library:
    p = SmartStrip("192.168.1.105")

    # change state of all outlets
    p.turn_on()
    p.turn_off()

    # change state of a single outlet
    p.turn_on(index=1)

    # query and print current state of all outlets
    print(p.get_state())

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    def __init__(
        self,
        host: str,
        protocol: TPLinkSmartHomeProtocol = None,
        cache_ttl: int = 3,
        *,
        ioloop=None
    ) -> None:
        SmartPlug.__init__(
            self, host=host, protocol=protocol, cache_ttl=cache_ttl, ioloop=ioloop
        )
        self.emeter_type = "emeter"
        self._device_type = DeviceType.Strip
        self.plugs = {}

        sys_info = self.sync.get_sys_info()
        children = sys_info["children"]
        self.num_children = len(children)
        for plug in range(self.num_children):
            self.plugs[plug] = SmartPlug(
                host,
                protocol,
                context=children[plug]["id"],
                cache_ttl=cache_ttl,
                ioloop=ioloop,
            )

    def raise_for_index(self, index: int):
        """
        Raises SmartStripException if the plug index is out of bounds

        :param index: plug index to check
        :raises SmartStripException: index out of bounds
        """
        if index not in range(self.num_children):
            raise SmartStripException("plug index of %d " "is out of bounds" % index)

    async def get_state(self, *, index=-1) -> Dict[int, str]:
        """Retrieve the switch state

        :returns: list with the state of each child plug
                  STATE_ON
                  STATE_OFF
        :rtype: dict
        """

        def _state_for_bool(_bool):
            return SmartPlug.STATE_ON if _bool else SmartPlug.STATE_OFF

        is_on = await self.get_is_on(index=index)
        if isinstance(is_on, bool):
            return _state_for_bool(is_on)

        return {k: _state_for_bool(v) for k, v in is_on.items()}

    def set_state(self, value: str, *, index: int = -1):
        """Sets the state of a plug on the strip

        :param value: one of
                    STATE_ON
                    STATE_OFF
        :param index: plug index (-1 for all)
        :raises ValueError: on invalid state
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            self.state = value
        else:
            self.raise_for_index(index)
            self.plugs[index].state = value

    async def is_on(self) -> bool:
        """Return if any of the outlets are on"""
        states = await self.get_state()
        return any(state == "ON" for state in states.values())

    async def get_is_on(self, *, index: int = -1) -> Any:
        """
        Returns whether device is on.

        :param index: plug index (-1 for all)
        :return: True if device is on, False otherwise, Dict without index
        :rtype: bool if index is provided
                Dict[int, bool] if no index provided
        :raises SmartStripException: index out of bounds
        """
        sys_info = await self.get_sys_info()
        children = sys_info["children"]
        if index < 0:
            is_on = {}
            for plug in range(self.num_children):
                is_on[plug] = bool(children[plug]["state"])
            return is_on
        else:
            self.raise_for_index(index)
            return bool(children[index]["state"])

    async def get_is_off(self, *, index: int = -1) -> Any:
        is_on = await self.get_is_on(index=index)
        if isinstance(is_on, bool):
            return not is_on
        else:
            return {k: not v for k, v in is_on}

    async def turn_on(self, *, index: int = -1):
        """
        Turns outlets on

        :param index: plug index (-1 for all)
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            await self._query_helper("system", "set_relay_state", {"state": 1})
        else:
            self.raise_for_index(index)
            await self.plugs[index].turn_on()

    async def turn_off(self, *, index: int = -1):
        """
        Turns outlets off

        :param index: plug index (-1 for all)
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            await self._query_helper("system", "set_relay_state", {"state": 0})
        else:
            self.raise_for_index(index)
            await self.plugs[index].turn_off()

    async def get_max_on_since(self) -> datetime:
        """Returns the maximum on-time of all outlets."""
        on_since = await self.get_on_since(index=-1)
        return max(v for v in on_since.values())

    async def get_on_since(self, *, index: Optional[int] = None) -> Any:
        """
        Returns pretty-printed on-time

        :param index: plug index (-1 for all)
        :return: datetime for on since
        :rtype: datetime with index
                Dict[int, str] without index
        :raises SmartStripException: index out of bounds
        """
        if index is None:
            return await self.get_max_on_since()

        if index < 0:
            on_since = {}
            sys_info = await self.get_sys_info()
            children = sys_info["children"]

            for plug in range(self.num_children):
                child_ontime = children[plug]["on_time"]
                on_since[plug] = datetime.datetime.now() - datetime.timedelta(
                    seconds=child_ontime
                )
            return on_since
        else:
            self.raise_for_index(index)
            return await self.plugs[index].get_on_since()

    async def get_state_information(self) -> Dict[str, Any]:
        """
        Returns strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        :rtype: dict
        """
        state = {"LED state": await self.get_led()}  # XXX: from where?
        is_on = await self.get_is_on()
        on_since = await self.get_on_since(index=-1)
        for plug_index in range(self.num_children):
            plug_number = plug_index + 1
            if is_on[plug_index]:
                state["Plug %d on since" % plug_number] = on_since[plug_index]

        return state

    async def get_emeter_realtime(self, *, index: int = -1) -> Optional[Any]:
        """
        Retrieve current energy readings from device

        :param index: plug index (-1 for all)
        :returns: list of current readings or None
        :rtype: Dict, Dict[int, Dict], None
                Dict if index is provided
                Dict[int, Dict] if no index provided
                None if device has no energy meter or error occurred
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not await self.get_has_emeter():  # pragma: no cover
            raise SmartStripException("Device has no emeter")

        if index < 0:
            emeter_status = {}
            for plug in range(self.num_children):
                emeter_status[plug] = await self.plugs[plug].get_emeter_realtime()
            return emeter_status
        else:
            self.raise_for_index(index)
            return await self.plugs[index].get_emeter_realtime()

    async def current_consumption(self, *, index: int = -1) -> Optional[Any]:
        """
        Get the current power consumption in Watts.

        :param index: plug index (-1 for all)
        :return: the current power consumption in Watts.
                 None if device has no energy meter.
        :rtype: Dict, Dict[int, Dict], None
                Dict if index is provided
                Dict[int, Dict] if no index provided
                None if device has no energy meter or error occurred
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not await self.get_has_emeter():  # pragma: no cover
            raise SmartStripException("Device has no emeter")

        if index < 0:
            consumption = {}
            emeter_reading = await self.get_emeter_realtime()
            for plug in range(self.num_children):
                response = EmeterStatus(emeter_reading[plug])
                consumption[plug] = response["power"]
            return consumption
        else:
            self.raise_for_index(index)
            response = EmeterStatus(await self.get_emeter_realtime(index=index))
            return response["power"]

    async def get_icon(self):
        """Override for base class icon property, SmartStrip and children do not
        have icons so we return dummy strings.
        """
        return {"icon": "SMARTSTRIP-DUMMY", "hash": "SMARTSTRIP-DUMMY"}

    async def get_alias(self, *, index: Optional[int] = None) -> Union[str, Dict[int, str]]:
        """Gets the alias for a plug.

        :param index: plug index (-1 for all)
        :return: the current power consumption in Watts.
                 None if device has no energy meter.
        :rtype: str if index is provided
                Dict[int, str] if no index provided
        :raises SmartStripException: index out of bounds
        """
        if index is None:
            return await super().get_alias()

        sys_info = await self.get_sys_info()
        children = sys_info["children"]

        if index < 0:
            alias = {}
            for plug in range(self.num_children):
                alias[plug] = children[plug]["alias"]
            return alias
        else:
            self.raise_for_index(index)
            return children[index]["alias"]

    async def set_alias(self, alias: str, *, index: Optional[int] = None):
        """Sets the alias for a plug

        :param index: plug index
        :param alias: new alias
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        # Renaming the whole strip
        if index is None:
            return await super().set_alias(alias)

        self.raise_for_index(index)
        await self.plugs[index].set_alias(alias)

    async def get_emeter_daily(
        self, year: int = None, month: int = None, kwh: bool = True, *, index: int = -1
    ) -> Dict:
        """Retrieve daily statistics for a given month

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistics (default: this
                      month)
        :param kwh: return usage in kWh (default: True)
        :return: mapping of day of month to value
                 None if device has no energy meter or error occurred
        :rtype: dict
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not await self.get_has_emeter():  # pragma: no cover
            raise SmartStripException("Device has no emeter")

        emeter_daily = {}
        if index < 0:
            for plug in range(self.num_children):
                emeter_daily = await self.plugs[plug].get_emeter_daily(
                    year=year, month=month, kwh=kwh
                )
            return emeter_daily
        else:
            self.raise_for_index(index)
            return await self.plugs[index].get_emeter_daily(
                year=year, month=month, kwh=kwh
            )

    async def get_emeter_monthly(
        self, year: int = None, kwh: bool = True, *, index: int = -1
    ) -> Dict:
        """Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
                 None if device has no energy meter
        :rtype: dict
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not await self.get_has_emeter():  # pragma: no cover
            raise SmartStripException("Device has no emeter")

        emeter_monthly = {}
        if index < 0:
            for plug in range(self.num_children):
                emeter_monthly[plug] = await self.plugs[plug].get_emeter_monthly(
                    year=year, kwh=kwh
                )
            return emeter_monthly
        else:
            self.raise_for_index(index)
            return await self.plugs[index].get_emeter_monthly(year=year, kwh=kwh)

    async def erase_emeter_stats(self, *, index: int = -1) -> bool:
        """Erase energy meter statistics

        :param index: plug index (-1 for all)
        :return: True if statistics were deleted
                 False if device has no energy meter.
        :rtype: bool
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not await self.get_has_emeter():  # pragma: no cover
            raise SmartStripException("Device has no emeter")

        if index < 0:
            for plug in range(self.num_children):
                await self.plugs[plug].erase_emeter_stats()
        else:
            self.raise_for_index(index)
            await self.plugs[index].erase_emeter_stats()

        # As query_helper raises exception in case of failure, we have
        # succeeded when we are this far.
        return True
