"""Implementation of brightness module."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...exceptions import KasaException
from ...interfaces.light import HSV, ColorTempRange
from ...interfaces.light import Light as LightInterface
from ..iotmodule import IotModule

if TYPE_CHECKING:
    from ..iotbulb import IotBulb
    from ..iotdimmer import IotDimmer


BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100


class Light(IotModule, LightInterface):
    """Implementation of brightness module."""

    _device: IotBulb | IotDimmer

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    def _get_bulb_device(self) -> IotBulb | None:
        if self._device.is_bulb or self._device.is_light_strip:
            return cast("IotBulb", self._device)
        return None

    @property  # type: ignore
    def is_dimmable(self) -> int:
        """Whether the bulb supports brightness changes."""
        return self._device.is_dimmable

    @property  # type: ignore
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        return self._device.brightness

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> None:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        return await self._device.set_brightness(brightness, transition=transition)

    @property
    def is_color(self) -> bool:
        """Whether the light supports color changes."""
        if (bulb := self._get_bulb_device()) is None:
            return False
        return bulb.is_color

    @property
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        if (bulb := self._get_bulb_device()) is None:
            return False
        return bulb.is_variable_color_temp

    @property
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        if (bulb := self._get_bulb_device()) is None:
            return False
        return bulb.has_effects

    @property
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if (bulb := self._get_bulb_device()) is None or not bulb.is_color:
            raise KasaException("Light does not support color.")
        return bulb.hsv

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> None:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """
        if (bulb := self._get_bulb_device()) is None or not bulb.is_color:
            raise KasaException("Light does not support color.")
        await bulb.set_hsv(hue, saturation, value, transition=transition)

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if (bulb := self._get_bulb_device()) is None or not bulb.is_variable_color_temp:
            raise KasaException("Light does not support colortemp.")
        return bulb.valid_temperature_range

    @property
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""
        if (bulb := self._get_bulb_device()) is None or not bulb.is_variable_color_temp:
            raise KasaException("Light does not support colortemp.")
        return bulb.color_temp

    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: int | None = None
    ) -> None:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """
        if (bulb := self._get_bulb_device()) is None or not bulb.is_variable_color_temp:
            raise KasaException("Light does not support colortemp.")
        await bulb.set_color_temp(temp, brightness=brightness, transition=transition)
