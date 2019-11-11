import re
from typing import Any, Dict, Tuple

from pyHS100.protocol import TPLinkSmartHomeProtocol
from pyHS100.smartdevice import DeviceType, SmartDevice, SmartDeviceException

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

    async def is_color(self) -> bool:
        """Whether the bulb supports color changes.

        :return: True if the bulb supports color changes, False otherwise
        :rtype: bool
        """
        sys_info = await self.get_sys_info()
        return bool(sys_info["is_color"])

    async def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes.

        :return: True if the bulb supports brightness changes, False otherwise
        :rtype: bool
        """
        sys_info = await self.get_sys_info()
        return bool(sys_info["is_dimmable"])

    async def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes.

        :return: True if the bulb supports color temperature changes, False
        otherwise
        :rtype: bool
        """
        sys_info = await self.get_sys_info()
        return bool(sys_info["is_variable_color_temp"])

    async def get_valid_temperature_range(self) -> Tuple[int, int]:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimun, maximum)
        :rtype: tuple
        """
        if not await self.is_variable_color_temp():
            return (0, 0)
        for model, temp_range in TPLINK_KELVIN.items():
            sys_info = await self.get_sys_info()
            if re.match(model, sys_info["model"]):
                return temp_range
        return (0, 0)

    async def get_light_state(self) -> Dict:
        """Query the light state."""
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def set_light_state(self, state: Dict) -> Dict:
        """Set the light state."""
        return await self._query_helper(
            self.LIGHT_SERVICE, "transition_light_state", state
        )

    async def get_hsv(self) -> Tuple[int, int, int]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        :rtype: tuple
        """

        if not await self.is_color():
            raise SmartDeviceException("Bulb does not support color.")

        light_state = await self.get_light_state()
        if not await self.is_on():
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

    async def set_hsv(self, hue: int, saturation: int, value: int):
        """Set new HSV.

        :param tuple state: hue, saturation and value (degrees, %, %)
        """
        if not await self.is_color():
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

    async def get_color_temp(self) -> int:
        """Return color temperature of the device.

        :return: Color temperature in Kelvin
        :rtype: int
        """
        if not await self.is_variable_color_temp():
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = await self.get_light_state()
        if not await self.is_on():
            return int(light_state["dft_on_state"]["color_temp"])
        else:
            return int(light_state["color_temp"])

    async def set_color_temp(self, temp: int) -> None:
        """Set the color temperature of the device.

        :param int temp: The new color temperature, in Kelvin
        """
        if not await self.is_variable_color_temp():
            raise SmartDeviceException("Bulb does not support colortemp.")

        valid_temperature_range = await self.get_valid_temperature_range()
        if temp < valid_temperature_range[0] or temp > valid_temperature_range[1]:
            raise ValueError(
                "Temperature should be between {} "
                "and {}".format(*valid_temperature_range)
            )

        light_state = {"color_temp": temp}
        await self.set_light_state(light_state)

    async def get_brightness(self) -> int:
        """Current brightness of the device.

        :return: brightness in percent
        :rtype: int
        """
        if not await self.is_dimmable():  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = await self.get_light_state()
        if not await self.is_on():
            return int(light_state["dft_on_state"]["brightness"])
        else:
            return int(light_state["brightness"])

    async def set_brightness(self, brightness: int) -> None:
        """Set the current brightness of the device.

        :param int brightness: brightness in percent
        """
        if not await self.is_dimmable():  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        await self.set_light_state(light_state)

    async def get_state_information(self) -> Dict[str, Any]:
        """Return bulb-specific state information.

        :return: Bulb information dict, keys in user-presentable form.
        :rtype: dict
        """
        info = {
            "Brightness": await self.get_brightness(),
            "Is dimmable": await self.is_dimmable(),
        }  # type: Dict[str, Any]
        if await self.is_variable_color_temp():
            info["Color temperature"] = await self.get_color_temp()
            info["Valid temperature range"] = await self.get_valid_temperature_range()
        if await self.is_color():
            info["HSV"] = await self.get_hsv()

        return info

    async def is_on(self) -> bool:
        """Return whether the device is on."""
        light_state = await self.get_light_state()
        return bool(light_state["on_off"])

    async def turn_off(self) -> None:
        """Turn the bulb off."""
        await self.set_light_state({"on_off": 0})

    async def turn_on(self) -> None:
        """Turn the bulb on."""
        await self.set_light_state({"on_off": 1})

    async def get_has_emeter(self) -> bool:
        return True
