"""Module for tapo-branded smart bulbs (L5**)."""

from __future__ import annotations

from typing import cast

from ..bulb import HSV, Bulb, BulbPreset, ColorTempRange
from ..exceptions import KasaException
from .modules.colormodule import ColorModule
from .modules.colortemp import ColorTemperatureModule
from .smartdevice import SmartDevice

AVAILABLE_EFFECTS = {
    "L1": "Party",
    "L2": "Relax",
}


class SmartBulb(SmartDevice, Bulb):
    """Representation of a TP-Link Tapo Bulb.

    Documentation TBD. See :class:`~kasa.iot.Bulb` for now.
    """

    @property
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""
        return "ColorModule" in self.modules

    @property
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""
        return "Brightness" in self.modules

    @property
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""
        return "ColorTemperatureModule" in self.modules

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        if not self.is_variable_color_temp:
            raise KasaException("Color temperature not supported")

        return cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).valid_temperature_range

    @property
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return "dynamic_light_effect_enable" in self._info

    @property
    def effect(self) -> dict:
        """Return effect state.

        This follows the format used by SmartLightStrip.

        Example:
            {'brightness': 50,
             'custom': 0,
             'enable': 0,
             'id': '',
             'name': ''}
        """
        # If no effect is active, dynamic_light_effect_id does not appear in info
        current_effect = self._info.get("dynamic_light_effect_id", "")
        data = {
            "brightness": self.brightness,
            "enable": current_effect != "",
            "id": current_effect,
            "name": AVAILABLE_EFFECTS.get(current_effect, ""),
        }

        return data

    @property
    def effect_list(self) -> list[str] | None:
        """Return built-in effects list.

        Example:
            ['Party', 'Relax', ...]
        """
        return list(AVAILABLE_EFFECTS.keys()) if self.has_effects else None

    @property
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """
        if not self.is_color:
            raise KasaException("Bulb does not support color.")

        return cast(ColorModule, self.modules["ColorModule"]).hsv

    @property
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""
        if not self.is_variable_color_temp:
            raise KasaException("Bulb does not support colortemp.")

        return cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).color_temp

    @property
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise KasaException("Bulb is not dimmable.")

        return self._info.get("brightness", -1)

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

        return await cast(ColorModule, self.modules["ColorModule"]).set_hsv(
            hue, saturation, value
        )

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
        return await cast(
            ColorTemperatureModule, self.modules["ColorTemperatureModule"]
        ).set_color_temp(temp)

    def _raise_for_invalid_brightness(self, value: int):
        """Raise error on invalid brightness value."""
        if not isinstance(value, int) or not (1 <= value <= 100):
            raise ValueError(f"Invalid brightness value: {value} (valid range: 1-100%)")

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

        self._raise_for_invalid_brightness(brightness)

        return await self.protocol.query(
            {"set_device_info": {"brightness": brightness}}
        )

    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> None:
        """Set an effect on the device."""
        raise NotImplementedError()

    @property
    def presets(self) -> list[BulbPreset]:
        """Return a list of available bulb setting presets."""
        return []
