"""Module for tapo-branded smart bulbs (L5**)."""
from typing import Dict, List, Optional

from ..exceptions import SmartDeviceException
from ..smartbulb import HSV, ColorTempRange, SmartBulb, SmartBulbPreset
from .tapodevice import TapoDevice

AVAILABLE_EFFECTS = {
    "L1": "Party",
    "L2": "Relax",
}


class TapoBulb(TapoDevice, SmartBulb):
    @property
    def is_color(self) -> bool:
        # TODO: this makes an assumption that only color bulbs report this
        return "hue" in self._info

    @property
    def is_dimmable(self) -> bool:
        # TODO: this makes an assumption that only dimmables report this
        return "brightness" in self._info

    @property
    def is_variable_color_temp(self) -> bool:
        # TODO: this makes an assumption, that only ct bulbs report this
        return bool(self._info.get("color_temp_range", False))

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """
        ct_range = self._info.get("color_temp_range", [0, 0])
        return ColorTempRange(min=ct_range[0], max=ct_range[1])

    @property
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""
        return "dynamic_light_effect_enable" in self._info

    @property
    def effect(self) -> Dict:
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
    def effect_list(self) -> Optional[List[str]]:
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
            raise SmartDeviceException("Bulb does not support color.")

        h, s, v = (
            self._info.get("hue", 0),
            self._info.get("saturation", 0),
            self._info.get("brightness", 0),
        )

        return HSV(hue=h, saturation=s, value=v)

    @property
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        return self._info.get("color_temp", -1)

    @property
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        return self._info.get("brightness", -1)

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: Optional[int] = None,
        *,
        transition: Optional[int] = None,
    ) -> Dict:
        if not self.is_color:
            raise SmartDeviceException("Bulb does not support color.")

        return await self.protocol.query(
            {
                "set_device_info": {
                    "hue": hue,
                    "saturation": saturation,
                    "brightness": value,
                }
            }
        )

    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: Optional[int] = None
    ) -> Dict:
        # TODO: Decide how to handle brightness and transition
        # TODO: Note, trying to set brightness at the same time
        #  with color_temp causes error -1008
        if not self.is_variable_color_temp:
            raise SmartDeviceException("Bulb does not support colortemp.")

        return await self.protocol.query({"set_device_info": {"color_temp": temp}})

    async def set_brightness(
        self, brightness: int, *, transition: Optional[int] = None
    ) -> Dict:
        # TODO: Decide how to handle transitions
        if not self.is_dimmable:  # pragma: no cover
            raise SmartDeviceException("Bulb is not dimmable.")

        return await self.protocol.query(
            {"set_device_info": {"brightness": brightness}}
        )

    # Default state information, should be made to settings
    """
    "info": {
        "default_states": {
        "re_power_type": "always_on",
        "type": "last_states",
        "state": {
            "brightness": 36,
            "hue": 0,
            "saturation": 0,
            "color_temp": 2700,
        },
    },
    """

    async def set_effect(
        self,
        effect: str,
        *,
        brightness: Optional[int] = None,
        transition: Optional[int] = None,
    ) -> None:
        """Set an effect on the device."""
        raise NotImplementedError()
        # TODO: the code below does to activate the effect but gives no error
        return await self.protocol.query(
            {
                "set_device_info": {
                    "dynamic_light_effect_enable": 1,
                    "dynamic_light_effect_id": effect,
                }
            }
        )

    @property
    def presets(self) -> List[SmartBulbPreset]:
        return []
