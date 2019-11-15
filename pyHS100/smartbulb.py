"""Module for bulbs."""
import re
from typing import Any, Dict, Optional, Tuple

from pyHS100.protocol import TPLinkSmartHomeProtocol
from pyHS100.smartdevice import (
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

    Usage example when used as library:
    ```python
    p = SmartBulb("192.168.1.105")

    # print the devices alias
    print(p.sync.alias)

    # change state of bulb
    p.sync.turn_on()
    p.sync.turn_off()

    # query and print current state of plug
    print(p.sync.state_information())

    # check whether the bulb supports color changes
    if p.sync.is_color():

    # set the color to an HSV tuple
    p.sync.set_hsv(180, 100, 100)

    # get the current HSV value
    print(p.sync.hsv())

    # check whether the bulb supports setting color temperature
    if p.sync.is_variable_color_temp():
        # set the color temperature in Kelvin
        p.sync.set_color_temp(3000)

        # get the current color temperature
        print(p.sync.color_temp)

    # check whether the bulb is dimmable
    if p.is_dimmable:

    # set the bulb to 50% brightness
    p.sync.set_brightness(50)

    # check the current brightness
    print(p.brightness)
    ```

    Omit the `sync` attribute to get coroutines.

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
        *,
        ioloop=None,
    ) -> None:
        SmartDevice.__init__(
            self,
            host=host,
            protocol=protocol,
            context=context,
            cache_ttl=cache_ttl,
            ioloop=ioloop,
        )
        self.emeter_type = "smartlife.iot.common.emeter"
        self._device_type = DeviceType.Bulb
        self._light_state = None

    @property
    @requires_update
    def is_color(self) -> bool:
        """Whether the bulb supports color changes.

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_color"])

    @property
    @requires_update
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes.

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_dimmable"])

    @property
    @requires_update
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes.

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        sys_info = self.sys_info
        return bool(sys_info["is_variable_color_temp"])

    @property
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

    async def update(self):
        """Update `sys_info and `light_state`."""
        self._sys_info = await self.get_sys_info()
        self._light_state = await self.get_light_state()

    @property
    @requires_update
    def light_state(self) -> Optional[Dict[str, Dict]]:
        """Query the light state."""
        return self._light_state

    async def get_light_state(self) -> Dict[str, Dict]:
        """Query the light state."""
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def set_light_state(self, state: Dict) -> Dict:
        """Set the light state."""
        light_state = await self._query_helper(
            self.LIGHT_SERVICE, "transition_light_state", state
        )
        await self.update()
        return light_state

    @property
    @requires_update
    def hsv(self) -> Tuple[int, int, int]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        :rtype: tuple
        """
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        light_state = self.light_state
        if not self.is_on:
            hue = light_state["dft_on_state"]["hue"]
            saturation = light_state["dft_on_state"]["saturation"]
            value = light_state["dft_on_state"]["brightness"]
        else:
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

    @property
    @requires_update
    def color_temp(self) -> int:
        """Return color temperature of the device.

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = self.light_state
        if not self.is_on:
            return int(light_state["dft_on_state"]["color_temp"])
        else:
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

    @property
    @requires_update
    def brightness(self) -> int:
        """Return the current brightness.

        :return: brightness in percent
        :rtype: int
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = self.light_state
        if not self.is_on:
            return int(light_state["dft_on_state"]["brightness"])
        else:
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

    @property
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

    @property
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

    @property
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the bulb has an emeter."""
        return True
