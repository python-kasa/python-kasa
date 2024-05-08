"""Module for led controls."""

from __future__ import annotations

from dataclasses import asdict

from ...exceptions import KasaException
from ...interfaces.light import HSV, ColorTempRange, LightState
from ...interfaces.light import Light as LightInterface
from ...module import Module
from ..smartmodule import SmartModule


class Light(SmartModule, LightInterface):
    """Implementation of a light."""

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        return Module.Color in self._device.modules

    @property
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        return Module.Brightness in self._device.modules

    @property
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        return Module.ColorTemperature in self._device.modules

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self.is_variable_color_temp:
            raise KasaException("Color temperature not supported")

        return self._device.modules[Module.ColorTemperature].valid_temperature_range

    @property
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            raise KasaException("Bulb does not support color.")

        return self._device.modules[Module.Color].hsv

    @property
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""
        if not self.is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")

        return self._device.modules[Module.ColorTemperature].color_temp

    @property
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return self._device.modules[Module.Brightness].brightness

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> dict:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value between 1 and 100
        :param int transition: transition in milliseconds.
        """
        if not self.is_color:
            raise KasaException("Bulb does not support color.")

        return await self._device.modules[Module.Color].set_hsv(hue, saturation, value)

    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: int | None = None
    ) -> dict:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if not self.is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")
        return await self._device.modules[Module.ColorTemperature].set_color_temp(temp)

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self.is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return await self._device.modules[Module.Brightness].set_brightness(brightness)

    @property
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return Module.LightEffect in self._device.modules

    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
        state_dict = asdict(state)
        # brightness of 0 turns off the light, it's not a valid brightness
        if state.brightness and state.brightness == 0:
            state_dict["device_on"] = False
            del state_dict["brightness"]

        params = {k: v for k, v in state_dict.items() if v is not None}
        return await self.call("set_device_info", params)
