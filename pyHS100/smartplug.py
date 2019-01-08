import datetime
import logging
from typing import Any, Dict, Optional

from pyHS100 import SmartDevice

_LOGGER = logging.getLogger(__name__)


class SmartPlug(SmartDevice):
    """Representation of a TP-Link Smart Switch.

    Usage example when used as library:
    p = SmartPlug("192.168.1.105")
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
    # switch states
    SWITCH_STATE_ON = 'ON'
    SWITCH_STATE_OFF = 'OFF'
    SWITCH_STATE_UNKNOWN = 'UNKNOWN'

    def __init__(self,
                 host: str,
                 protocol: 'TPLinkSmartHomeProtocol' = None,
                 context: str = None) -> None:
        SmartDevice.__init__(self, host, protocol, context)
        self._type = "emeter"

    @property
    def state(self) -> str:
        """
        Retrieve the switch state

        :returns: one of
                  SWITCH_STATE_ON
                  SWITCH_STATE_OFF
                  SWITCH_STATE_UNKNOWN
        :rtype: str
        """
        relay_state = self.sys_info['relay_state']

        if relay_state == 0:
            return SmartPlug.SWITCH_STATE_OFF
        elif relay_state == 1:
            return SmartPlug.SWITCH_STATE_ON
        else:
            _LOGGER.warning("Unknown state %s returned.", relay_state)
            return SmartPlug.SWITCH_STATE_UNKNOWN

    @state.setter
    def state(self, value: str):
        """
        Set the new switch state

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

    @property
    def brightness(self) -> Optional[int]:
        """
        Current brightness of the device, if supported.
        Will return a a range between 0 - 100.

        :returns: integer
        :rtype: int

        """
        if not self.is_dimmable:
            return None

        return int(self.sys_info['brightness'])

    @brightness.setter
    def brightness(self, value: int):
        """
        Set the new switch brightness level.

        Note:
        When setting brightness, if the light is not
        already on, it will be turned on automatically.

        :param value: integer between 1 and 100

        """
        if not self.is_dimmable:
            return

        if not isinstance(value, int):
            raise ValueError("Brightness must be integer, "
                             "not of %s.", type(value))
        elif value > 0 and value <= 100:
            self.turn_on()
            self._query_helper("smartlife.iot.dimmer", "set_brightness",
                               {"brightness": value})
        else:
            raise ValueError("Brightness value %s is not valid.", value)

    @property
    def is_dimmable(self):
        """
        Whether the switch supports brightness changes

        :return: True if switch supports brightness changes, False otherwise
        :rtype: bool
        """
        return "brightness" in self.sys_info

    @property
    def has_emeter(self):
        """
        Returns whether device has an energy meter.
        :return: True if energy meter is available
                 False otherwise
        """
        features = self.sys_info['feature'].split(':')
        return SmartDevice.FEATURE_ENERGY_METER in features

    @property
    def is_on(self) -> bool:
        """
        Returns whether device is on.

        :return: True if device is on, False otherwise
        """
        return bool(self.sys_info['relay_state'])

    def turn_on(self):
        """
        Turn the switch on.

        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 1})

    def turn_off(self):
        """
        Turn the switch off.

        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_relay_state", {"state": 0})

    @property
    def led(self) -> bool:
        """
        Returns the state of the led.

        :return: True if led is on, False otherwise
        :rtype: bool
        """
        return bool(1 - self.sys_info["led_off"])

    @led.setter
    def led(self, state: bool):
        """
        Sets the state of the led (night mode)

        :param bool state: True to set led on, False to set led off
        :raises SmartDeviceException: on error
        """
        self._query_helper("system", "set_led_off", {"off": int(not state)})

    @property
    def on_since(self) -> datetime.datetime:
        """
        Returns pretty-printed on-time

        :return: datetime for on since
        :rtype: datetime
        """
        if self.context:
            for plug in self.sys_info["children"]:
                if plug["id"] == self.context:
                    on_time = plug["on_time"]
                    break
        else:
            on_time = self.sys_info["on_time"]

        return datetime.datetime.now() - datetime.timedelta(seconds=on_time)

    @property
    def state_information(self) -> Dict[str, Any]:
        """
        Return switch-specific state information.

        :return: Switch information dict, keys in user-presentable form.
        :rtype: dict
        """
        info = {
            'LED state': self.led,
            'On since': self.on_since
        }
        if self.is_dimmable:
            info["Brightness"] = self.brightness
        return info
