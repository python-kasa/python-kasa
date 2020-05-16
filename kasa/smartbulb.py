"""Module for bulbs."""
import re
from typing import Any, Dict, Tuple, cast

from kasa.smartdevice import (
    DeviceType,
    SmartDevice,
    SmartDeviceException,
    requires_update,
)

TPLINK_KELVIN = {
    "LB130": (2500, 9000),
    "LB120": (2700, 6500),
    "LB230": (2500, 9000),
    "KB130": (2500, 9000),
    "KL130": (2500, 9000),
    r"KL120\(EU\)": (2700, 6500),
    r"KL120\(US\)": (2700, 5000),
}


class SmartBulb(SmartDevice):
    """Representation of a TP-Link Smart Bulb.

    Usage example:
    ```python
    p = SmartBulb("192.168.1.105")
    await p.update()

    # print the devices alias
    print(p.alias)

    # change state of bulb
    await p.turn_on()
    assert p.is_on
    await p.turn_off()

    # query and print current state of plug
    print(p.state_information)

    # check whether the bulb supports color changes
    if p.is_color:
        print("we got color!")
        # set the color to an HSV tuple
        await p.set_hsv(180, 100, 100)
        # get the current HSV value
        print(p.hsv)

    # check whether the bulb supports setting color temperature
    if p.is_variable_color_temp:
        # set the color temperature in Kelvin
        await p.set_color_temp(3000)

        # get the current color temperature
        print(p.color_temp)

    # check whether the bulb is dimmable
    if p.is_dimmable:
        # set the bulb to 50% brightness
        await p.set_brightness(50)

        # check the current brightness
        print(p.brightness)
    ```

    Errors reported by the device are raised as SmartDeviceExceptions,
    and should be handled by the user of the library.
    """

    LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"

    def __init__(self, host: str) -> None:
        super().__init__(host=host)
        self.emeter_type = "smartlife.iot.common.emeter"
        self._device_type = DeviceType.Bulb

    @property  # type: ignore
    @requires_update
    def is_color(self) -> bool:
        """Whether the bulb supports color changes.

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_color"])

    @property  # type: ignore
    @requires_update
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes.

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_dimmable"])

    @property  # type: ignore
    @requires_update
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes.

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_variable_color_temp"])

    @property  # type: ignore
    @requires_update
    def valid_temperature_range(self) -> Tuple[int, int]:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimun, maximum)
        :rtype: tuple
        """
        if not self.is_variable_color_temp:
            return (0, 0)
        for model, temp_range in TPLINK_KELVIN.items():
            sys_info = self.sys_info
            if re.match(model, sys_info["model"]):
                return temp_range
        return (0, 0)

    @property  # type: ignore
    @requires_update
    def light_state(self) -> Dict[str, str]:
        """Query the light state."""
        light_state = self._last_update["system"]["get_sysinfo"]["light_state"]
        if light_state is None:
            raise SmartDeviceException(
                "The device has no light_state or you have not called update()"
            )

        # if the bulb is off, its state is stored under a different key
        # as is_on property depends on on_off itself, we check it here manually
        is_on = light_state["on_off"]
        if not is_on:
            off_state = {**light_state["dft_on_state"], "on_off": is_on}
            return cast(dict, off_state)

        return light_state

    async def get_light_state(self) -> Dict[str, Dict]:
        """Query the light state."""
        # TODO: add warning and refer to use light.state?
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def set_light_state(self, state: Dict) -> Dict:
        """Set the light state."""
        light_state = await self._query_helper(
            self.LIGHT_SERVICE, "transition_light_state", state
        )
        await self.update()
        return light_state

    @property  # type: ignore
    @requires_update
    def hsv(self) -> Tuple[int, int, int]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        :rtype: tuple
        """
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        light_state = cast(dict, self.light_state)

        hue = light_state["hue"]
        saturation = light_state["saturation"]
        value = light_state["brightness"]

        return hue, saturation, value

    def _raise_for_invalid_brightness(self, value):
        if not isinstance(value, int) or not (0 <= value <= 100):
            raise ValueError(
                "Invalid brightness value: {} " "(valid range: 0-100%)".format(value)
            )

    @requires_update
    async def set_hsv(self, hue: int, saturation: int, value: int):
        """Set new HSV.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
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
        await self.set_light_state(light_state)

    @property  # type: ignore
    @requires_update
    def color_temp(self) -> int:
        """Return color temperature of the device.

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = self.light_state
        return int(light_state["color_temp"])

    @requires_update
    async def set_color_temp(self, temp: int) -> None:
        """Set the color temperature of the device.

        :param int temp: The new color temperature, in Kelvin
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        valid_temperature_range = self.valid_temperature_range
        if temp < valid_temperature_range[0] or temp > valid_temperature_range[1]:
            raise ValueError(
                "Temperature should be between {} "
                "and {}".format(*valid_temperature_range)
            )

        light_state = {"color_temp": temp}
        await self.set_light_state(light_state)

    @property  # type: ignore
    @requires_update
    def brightness(self) -> int:
        """Return the current brightness.

        :return: brightness in percent
        :rtype: int
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = self.light_state
        return int(light_state["brightness"])

    @requires_update
    async def set_brightness(self, brightness: int) -> None:
        """Set the brightness.

        :param int brightness: brightness in percent
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        await self.set_light_state(light_state)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return bulb-specific state information.

        :return: Bulb information dict, keys in user-presentable form.
        :rtype: dict
        """
        info: Dict[str, Any] = {
            "Brightness": self.brightness,
            "Is dimmable": self.is_dimmable,
        }
        if self.is_variable_color_temp:
            info["Color temperature"] = self.color_temp
            info["Valid temperature range"] = self.valid_temperature_range
        if self.is_color:
            info["HSV"] = self.hsv

        return info

    @property  # type: ignore
    @requires_update
    def is_on(self) -> bool:
        """Return whether the device is on."""
        light_state = self.light_state
        return bool(light_state["on_off"])

    async def turn_off(self) -> None:
        """Turn the bulb off."""
        await self.set_light_state({"on_off": 0})

    async def turn_on(self) -> None:
        """Turn the bulb on."""
        await self.set_light_state({"on_off": 1})

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the bulb has an emeter."""
        return True
