from pyHS100 import DeviceType, SmartDevice, SmartDeviceException
from .protocol import TPLinkSmartHomeProtocol
from deprecation import deprecated
import re
from datetime import datetime
from typing import Any, Dict, Tuple


TPLINK_KELVIN = {
    "LB130": (2500, 9000),
    "LB120": (2700, 6500),
    "LB230": (2500, 9000),
    "KB130": (2500, 9000),
    "KL130": (2500, 9000),
    "KL120\(EU\)": (2700, 6500),
    "KL120\(US\)": (2700, 5000),
}


class SmartBulb(SmartDevice):
    """Representation of a TP-Link Smart Bulb.

    Usage example when used as library:
    p = SmartBulb("192.168.1.105")

    # print the devices alias
    print(p.alias)

    # change state of bulb
    p.turn_on()
    p.turn_off()

    # query and print current state of plug
    print(p.state)

    # check whether the bulb supports color changes
    if p.is_color:

    # set the color to an HSV tuple
    p.set_hsv(180, 100, 100)
    # get the current HSV value
    print(p.hsv)

    # check whether the bulb supports setting color temperature
    if p.is_variable_color_temp:
    # set the color temperature in Kelvin
    p.set_color_temp(3000)
    # get the current color temperature
    print(p.color_temp)

    # check whether the bulb is dimmable
    if p.is_dimmable:
    # set the bulb to 50% brightness
    p.set_brightness(50)
    # check the current brightness
    print(p.brightness)

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"

    def __init__(
        self,
        host: str,
        protocol: TPLinkSmartHomeProtocol = None,
        context: str = None,
        cache_ttl: int = 3,
    ) -> None:
        SmartDevice.__init__(
            self, host=host, protocol=protocol, context=context, cache_ttl=cache_ttl
        )
        self.emeter_type = "smartlife.iot.common.emeter"
        self._device_type = DeviceType.Bulb

    @property
    def is_color(self) -> bool:
        """Whether the bulb supports color changes.

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info["is_color"])

    @property
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes.

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        return bool(self.sys_info["is_dimmable"])

    @property
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes.

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        return bool(self.sys_info["is_variable_color_temp"])

    @property
    def valid_temperature_range(self) -> Tuple[int, int]:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimun, maximum)
        :rtype: tuple
        """
        if not self.is_variable_color_temp:
            return (0, 0)
        for model, temp_range in TPLINK_KELVIN.items():
            if re.match(model, self.sys_info["model"]):
                return temp_range
        return (0, 0)

    def get_light_state(self) -> Dict:
        """Query the light state."""
        return self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    def set_light_state(self, state: Dict) -> Dict:
        """Set the light state."""
        return self._query_helper(self.LIGHT_SERVICE, "transition_light_state", state)

    @property
    def hsv(self) -> Tuple[int, int, int]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        :rtype: tuple
        """

        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        light_state = self.get_light_state()
        if not self.is_on:
            hue = light_state["dft_on_state"]["hue"]
            saturation = light_state["dft_on_state"]["saturation"]
            value = light_state["dft_on_state"]["brightness"]
        else:
            hue = light_state["hue"]
            saturation = light_state["saturation"]
            value = light_state["brightness"]

        return hue, saturation, value

    @hsv.setter  # type: ignore
    @deprecated(details="Use set_hsv()")
    def hsv(self, state: Tuple[int, int, int]):
        return self.set_hsv(state[0], state[1], state[2])

    def _raise_for_invalid_brightness(self, value):
        if not isinstance(value, int) or not (0 <= value <= 100):
            raise ValueError(
                "Invalid brightness value: {} " "(valid range: 0-100%)".format(value)
            )

    def set_hsv(self, hue: int, saturation: int, value: int):
        """Set new HSV.

        :param tuple state: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        if not isinstance(hue, int) or not (0 <= hue <= 360):
            raise ValueError(
                "Invalid hue value: {} " "(valid range: 0-360)".format(hue)
            )

        if not isinstance(saturation, int) or not (0 <= saturation <= 100):
            raise ValueError(
                "Invalid saturation value: {} "
                "(valid range: 0-100%)".format(saturation)
            )

        self._raise_for_invalid_brightness(value)

        light_state = {
            "hue": hue,
            "saturation": saturation,
            "brightness": value,
            "color_temp": 0,
        }
        self.set_light_state(light_state)

    @property
    def color_temp(self) -> int:
        """Return color temperature of the device.

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = self.get_light_state()
        if not self.is_on:
            return int(light_state["dft_on_state"]["color_temp"])
        else:
            return int(light_state["color_temp"])

    @color_temp.setter  # type: ignore
    @deprecated(details="use set_color_temp")
    def color_temp(self, temp: int) -> None:
        self.set_color_temp(temp)

    def set_color_temp(self, temp: int) -> None:
        """Set the color temperature of the device.

        :param int temp: The new color temperature, in Kelvin
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        if (
            temp < self.valid_temperature_range[0]
            or temp > self.valid_temperature_range[1]
        ):
            raise ValueError(
                "Temperature should be between {} "
                "and {}".format(*self.valid_temperature_range)
            )

        light_state = {"color_temp": temp}
        self.set_light_state(light_state)

    @property
    def brightness(self) -> int:
        """Current brightness of the device.

        :return: brightness in percent
        :rtype: int
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = self.get_light_state()
        if not self.is_on:
            return int(light_state["dft_on_state"]["brightness"])
        else:
            return int(light_state["brightness"])

    @brightness.setter  # type: ignore
    @deprecated(details="use set_brightness")
    def brightness(self, brightness: int) -> None:
        self.set_brightness(brightness)

    def set_brightness(self, brightness: int) -> None:
        """Set the current brightness of the device.

        :param int brightness: brightness in percent
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        self.set_light_state(light_state)

    @property  # type: ignore
    @deprecated(details="use is_on() and is_off()")
    def state(self) -> str:
        """Retrieve the bulb state.

        :returns: one of
                  STATE_ON
                  STATE_OFF
        :rtype: str
        """
        if self.is_on:
            return self.STATE_ON

        return self.STATE_OFF

    @state.setter  # type: ignore
    @deprecated(details="use turn_on() and turn_off()")
    def state(self, bulb_state: str) -> None:
        """Set the new bulb state.

        :param bulb_state: one of
                           STATE_ON
                           STATE_OFF
        """
        if bulb_state == self.STATE_ON:
            new_state = 1
        elif bulb_state == self.STATE_OFF:
            new_state = 0
        else:
            raise ValueError

        light_state = {"on_off": new_state}
        self.set_light_state(light_state)

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return bulb-specific state information.

        :return: Bulb information dict, keys in user-presentable form.
        :rtype: dict
        """
        info = {
            "Brightness": self.brightness,
            "Is dimmable": self.is_dimmable,
        }  # type: Dict[str, Any]
        if self.is_variable_color_temp:
            info["Color temperature"] = self.color_temp
            info["Valid temperature range"] = self.valid_temperature_range
        if self.is_color:
            info["HSV"] = self.hsv

        return info

    @property
    def is_on(self) -> bool:
        """Return whether the device is on."""
        light_state = self.get_light_state()
        return bool(light_state["on_off"])

    def turn_off(self) -> None:
        """Turn the bulb off."""
        self.set_light_state({"on_off": 0})

    def turn_on(self) -> None:
        """Turn the bulb on."""
        self.set_light_state({"on_off": 1})

    @property
    def has_emeter(self) -> bool:
        return True
