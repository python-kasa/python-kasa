"""Module for bulbs (LB*, KL*, KB*)."""
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
    "KL125": (2500, 6500),
    r"KL120\(EU\)": (2700, 6500),
    r"KL120\(US\)": (2700, 5000),
    r"KL430\(US\)": (2500, 9000),
}


class SmartBulb(SmartDevice):
    """Representation of a TP-Link Smart Bulb.

    To initialize, you have to await :func:`update()` at least once.
    This will allow accessing the properties using the exposed properties.

    All changes to the device are done using awaitable methods,
    which will not change the cached values, but you must await :func:`update()` separately.

    Errors reported by the device are raised as :class:`SmartDeviceException`s,
    and should be handled by the user of the library.

    Examples:
        >>> import asyncio
        >>> bulb = SmartBulb("127.0.0.1")
        >>> asyncio.run(bulb.update())
        >>> print(bulb.alias)
        KL130 office bulb

        Bulbs, like any other supported devices, can be turned on and off:

        >>> asyncio.run(bulb.turn_off())
        >>> asyncio.run(bulb.turn_on())
        >>> asyncio.run(bulb.update())
        >>> print(bulb.is_on)
        True

        You can use the is_-prefixed properties to check for supported features
        >>> bulb.is_dimmable
        True
        >>> bulb.is_color
        True
        >>> bulb.is_variable_color_temp
        True

        All known bulbs support changing the brightness:

        >>> bulb.brightness
        30
        >>> asyncio.run(bulb.set_brightness(50))
        >>> asyncio.run(bulb.update())
        >>> bulb.brightness
        50

        Bulbs supporting color temperature can be queried to know which range is accepted:

        >>> bulb.valid_temperature_range
        (2500, 9000)
        >>> asyncio.run(bulb.set_color_temp(3000))
        >>> asyncio.run(bulb.update())
        >>> bulb.color_temp
        3000

        Color bulbs can be adjusted by passing hue, saturation and value:

        >>> asyncio.run(bulb.set_hsv(180, 100, 80))
        >>> asyncio.run(bulb.update())
        >>> bulb.hsv
        (180, 100, 80)

        If you don't want to use the default transitions, you can pass `transition` in milliseconds.
        This applies to all transitions (turn_on, turn_off, set_hsv, set_color_temp, set_brightness).
        The following changes the brightness over a period of 10 seconds:

        >>> asyncio.run(bulb.set_brightness(100, transition=10_000))

    """

    LIGHT_SERVICE = "smartlife.iot.smartbulb.lightingservice"
    SET_LIGHT_METHOD = "transition_light_state"

    def __init__(self, host: str) -> None:
        super().__init__(host=host)
        self.emeter_type = "smartlife.iot.common.emeter"
        self._device_type = DeviceType.Bulb

    @property  # type: ignore
    @requires_update
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_color"])

    @property  # type: ignore
    @requires_update
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_dimmable"])

    @property  # type: ignore
    @requires_update
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        sys_info = self.sys_info
        return bool(sys_info["is_variable_color_temp"])

    @property  # type: ignore
    @requires_update
    def valid_temperature_range(self) -> Tuple[int, int]:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Color temperature not supported")
        for model, temp_range in TPLINK_KELVIN.items():
            sys_info = self.sys_info
            if re.match(model, sys_info["model"]):
                return temp_range

        raise SmartDeviceException(
            "Unknown color temperature range, please open an issue on github"
        )

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

    async def get_light_details(self) -> Dict[str, int]:
        """Return light details.

        Example:
            {'lamp_beam_angle': 290, 'min_voltage': 220, 'max_voltage': 240,
             'wattage': 5, 'incandescent_equivalent': 40, 'max_lumens': 450,
              'color_rendering_index': 80}
        """
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_details")

    async def get_turn_on_behavior(self) -> Dict:
        """Return the behavior for turning the bulb on.

        Example:
            {'soft_on': {'mode': 'last_status'},
            'hard_on': {'mode': 'last_status'}}
        """
        return await self._query_helper(self.LIGHT_SERVICE, "get_default_behavior")

    async def get_light_state(self) -> Dict[str, Dict]:
        """Query the light state."""
        # TODO: add warning and refer to use light.state?
        return await self._query_helper(self.LIGHT_SERVICE, "get_light_state")

    async def set_light_state(self, state: Dict, *, transition: int = None) -> Dict:
        """Set the light state."""
        if transition is not None:
            state["transition_period"] = transition

        # if no on/off is defined, turn on the light
        if "on_off" not in state:
            state["on_off"] = 1

        # This is necessary to allow turning on into a specific state
        state["ignore_default"] = 1

        light_state = await self._query_helper(
            self.LIGHT_SERVICE, self.SET_LIGHT_METHOD, state
        )
        return light_state

    @property  # type: ignore
    @requires_update
    def hsv(self) -> Tuple[int, int, int]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
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
    async def set_hsv(
        self, hue: int, saturation: int, value: int, *, transition: int = None
    ) -> Dict:
        """Set new HSV.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
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

        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def color_temp(self) -> int:
        """Return color temperature of the device in kelvin."""
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        light_state = self.light_state
        return int(light_state["color_temp"])

    @requires_update
    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: int = None
    ) -> Dict:
        """Set the color temperature of the device in kelvin.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
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
        if brightness is not None:
            light_state["brightness"] = brightness

        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        light_state = self.light_state
        return int(light_state["brightness"])

    @requires_update
    async def set_brightness(self, brightness: int, *, transition: int = None) -> Dict:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        self._raise_for_invalid_brightness(brightness)

        light_state = {"brightness": brightness}
        return await self.set_light_state(light_state, transition=transition)

    @property  # type: ignore
    @requires_update
    def state_information(self) -> Dict[str, Any]:
        """Return bulb-specific state information."""
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

    async def turn_off(self, *, transition: int = None, **kwargs) -> Dict:
        """Turn the bulb off.

        :param int transition: transition in milliseconds.
        """
        return await self.set_light_state({"on_off": 0}, transition=transition)

    async def turn_on(self, *, transition: int = None, **kwargs) -> Dict:
        """Turn the bulb on.

        :param int transition: transition in milliseconds.
        """
        return await self.set_light_state({"on_off": 1}, transition=transition)

    @property  # type: ignore
    @requires_update
    def has_emeter(self) -> bool:
        """Return that the bulb has an emeter."""
        return True
