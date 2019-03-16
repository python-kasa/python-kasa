import datetime
import logging
from typing import Any, Dict, Optional, Union

from pyHS100 import SmartPlug, SmartDeviceException, EmeterStatus

_LOGGER = logging.getLogger(__name__)


class SmartStripException(SmartDeviceException):
    """
    SmartStripException gets raised for errors specific to the smart strip.
    """
    pass


class SmartStrip(SmartPlug):
    """Representation of a TP-Link Smart Power Strip.

    Usage example when used as library:
    p = SmartStrip("192.168.1.105")
    # print the devices alias
    print(p.alias)
    # change state of plug
    p.state = "ON"
    p.state = "OFF"
    # query and print current state of plug
    print(p.state)

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.

    Note:
    The library references the same structure as defined for the D-Link Switch
    """

    def __init__(self,
                 host: str,
                 protocol: 'TPLinkSmartHomeProtocol' = None) -> None:
        SmartPlug.__init__(self, host, protocol)
        self.emeter_type = "emeter"
        self.plugs = {}
        children = self.sys_info["children"]
        self.num_children = len(children)
        for plug in range(self.num_children):
            self.plugs[plug] = SmartPlug(host, protocol,
                                         context=children[plug]["id"])

    def raise_for_index(self, index: int):
        """
        Raises SmartStripException if the plug index is out of bounds

        :param index: plug index to check
        :raises SmartStripException: index out of bounds
        """
        if index not in range(self.num_children):
            raise SmartStripException("plug index of %d "
                                      "is out of bounds" % index)

    @property
    def state(self) -> Dict[int, str]:
        """
        Retrieve the switch state

        :returns: list with the state of each child plug
                  SWITCH_STATE_ON
                  SWITCH_STATE_OFF
                  SWITCH_STATE_UNKNOWN
        :rtype: dict
        """
        states = {}
        children = self.sys_info["children"]
        for plug in range(self.num_children):
            relay_state = children[plug]["state"]

            if relay_state == 0:
                switch_state = SmartPlug.SWITCH_STATE_OFF
            elif relay_state == 1:
                switch_state = SmartPlug.SWITCH_STATE_ON
            else:
                _LOGGER.warning("Unknown state %s returned for plug %u.",
                                relay_state, plug)
                switch_state = SmartPlug.SWITCH_STATE_UNKNOWN

            states[plug] = switch_state

        return states

    @state.setter
    def state(self, value: str):
        """
        Sets the state of all plugs in the strip

        :param value: one of
                    SWITCH_STATE_ON
                    SWITCH_STATE_OFF
        :raises ValueError: on invalid state
        :raises SmartDeviceException: on error
        """
        if not isinstance(value, str):
            raise ValueError("State must be str, not of %s.", type(value))
        elif value.upper() == SmartPlug.SWITCH_STATE_ON:
            self.turn_on()
        elif value.upper() == SmartPlug.SWITCH_STATE_OFF:
            self.turn_off()
        else:
            raise ValueError("State %s is not valid.", value)

    def set_state(self, value: str, *, index: int = -1):
        """
        Sets the state of a plug on the strip

        :param value: one of
                    SWITCH_STATE_ON
                    SWITCH_STATE_OFF
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

    def is_on(self, *, index: int = -1) -> Any:
        """
        Returns whether device is on.

        :param index: plug index (-1 for all)
        :return: True if device is on, False otherwise, Dict without index
        :rtype: bool if index is provided
                Dict[int, bool] if no index provided
        :raises SmartStripException: index out of bounds
        """
        children = self.sys_info["children"]
        if index < 0:
            is_on = {}
            for plug in range(self.num_children):
                is_on[plug] = bool(children[plug]["state"])
            return is_on
        else:
            self.raise_for_index(index)
            return bool(children[index]["state"])

    def turn_on(self, *, index: int = -1):
        """
        Turns outlets on

        :param index: plug index (-1 for all)
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            self._query_helper("system", "set_relay_state", {"state": 1})
        else:
            self.raise_for_index(index)
            self.plugs[index].turn_on()

    def turn_off(self, *, index: int = -1):
        """
        Turns outlets off

        :param index: plug index (-1 for all)
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            self._query_helper("system", "set_relay_state", {"state": 0})
        else:
            self.raise_for_index(index)
            self.plugs[index].turn_off()

    def on_since(self, *, index: int = -1) -> Any:
        """
        Returns pretty-printed on-time

        :param index: plug index (-1 for all)
        :return: datetime for on since
        :rtype: datetime with index
                Dict[int, str] without index
        :raises SmartStripException: index out of bounds
        """
        if index < 0:
            on_since = {}
            children = self.sys_info["children"]
            for plug in range(self.num_children):
                on_since[plug] = \
                    datetime.datetime.now() - \
                    datetime.timedelta(seconds=children[plug]["on_time"])
            return on_since
        else:
            self.raise_for_index(index)
            return self.plugs[index].on_since

    @property
    def state_information(self) -> Dict[str, Any]:
        """
        Returns strip-specific state information.

        :return: Strip information dict, keys in user-presentable form.
        :rtype: dict
        """
        state = {'LED state': self.led}
        on_since = self.on_since()
        is_on = self.is_on()
        for plug_index in range(self.num_children):
            plug_number = plug_index + 1
            if is_on[plug_index]:
                state['Plug %d on since' % plug_number] = on_since[plug_index]

        return state

    def get_emeter_realtime(self, *, index: int = -1) -> Optional[Any]:
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
        if not self.has_emeter:
            return None

        if index < 0:
            emeter_status = {}
            for plug in range(self.num_children):
                emeter_status[plug] = self.plugs[plug].get_emeter_realtime()
            return emeter_status
        else:
            self.raise_for_index(index)
            return self.plugs[index].get_emeter_realtime()

    def current_consumption(self, *, index: int = -1) -> Optional[Any]:
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
        if not self.has_emeter:
            return None

        if index < 0:
            consumption = {}
            emeter_reading = self.get_emeter_realtime()
            for plug in range(self.num_children):
                response = EmeterStatus(emeter_reading[plug])
                consumption[plug] = response["power"]
            return consumption
        else:
            self.raise_for_index(index)
            response = EmeterStatus(self.get_emeter_realtime(index=index))
            return response["power"]

    @property
    def icon(self):
        """
        Override for base class icon property, SmartStrip and children do not
        have icons.

        :raises NotImplementedError: always
        """
        raise NotImplementedError("no icons for this device")

    def get_alias(self, *, index: int = -1) -> Union[str, Dict[int, str]]:
        """
        Gets the alias for a plug.

        :param index: plug index (-1 for all)
        :return: the current power consumption in Watts.
                 None if device has no energy meter.
        :rtype: str if index is provided
                Dict[int, str] if no index provided
        :raises SmartStripException: index out of bounds
        """
        children = self.sys_info["children"]

        if index < 0:
            alias = {}
            for plug in range(self.num_children):
                alias[plug] = children[plug]["alias"]
            return alias
        else:
            self.raise_for_index(index)
            return children[index]["alias"]

    def set_alias(self, alias: str, index: int):
        """
        Sets the alias for a plug

        :param index: plug index
        :param alias: new alias
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        self.raise_for_index(index)
        self.plugs[index].alias = alias

    def get_emeter_daily(self,
                         year: int = None,
                         month: int = None,
                         kwh: bool = True,
                         *,
                         index: int = -1) -> Optional[Dict]:
        """
        Retrieve daily statistics for a given month

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
        if not self.has_emeter:
            return None

        emeter_daily = {}
        if index < 0:
            for plug in range(self.num_children):
                emeter_daily = self.plugs[plug].get_emeter_daily(year=year,
                                                                 month=month,
                                                                 kwh=kwh)
            return emeter_daily
        else:
            self.raise_for_index(index)
            return self.plugs[index].get_emeter_daily(year=year,
                                                      month=month,
                                                      kwh=kwh)

    def get_emeter_monthly(self,
                           year: int = None,
                           kwh: bool = True,
                           *,
                           index: int = -1) -> Optional[Dict]:
        """
        Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :param kwh: return usage in kWh (default: True)
        :return: dict: mapping of month to value
                 None if device has no energy meter
        :rtype: dict
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not self.has_emeter:
            return None

        emeter_monthly = {}
        if index < 0:
            for plug in range(self.num_children):
                emeter_monthly = self.plugs[plug].get_emeter_monthly(year=year,
                                                                     kwh=kwh)
            return emeter_monthly
        else:
            self.raise_for_index(index)
            return self.plugs[index].get_emeter_monthly(year=year,
                                                        kwh=kwh)

    def erase_emeter_stats(self, *, index: int = -1) -> bool:
        """
        Erase energy meter statistics

        :param index: plug index (-1 for all)
        :return: True if statistics were deleted
                 False if device has no energy meter.
        :rtype: bool
        :raises SmartDeviceException: on error
        :raises SmartStripException: index out of bounds
        """
        if not self.has_emeter:
            return False

        if index < 0:
            for plug in range(self.num_children):
                self.plugs[plug].erase_emeter_stats()
        else:
            self.raise_for_index(index)
            self.plugs[index].erase_emeter_stats()

        # As query_helper raises exception in case of failure, we have
        # succeeded when we are this far.
        return True
