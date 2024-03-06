"""Implementation of color temp module."""
from typing import TYPE_CHECKING, Dict

from ...feature import Feature
from ..smartmodule import SmartModule
from ...bulb import ColorTempRange

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class ColorTemperatureModule(SmartModule):
    """Implementation of color temp module."""

    REQUIRED_COMPONENT = "color_temperature"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Color temperature",
                container=self,
                attribute_getter="color_temp",
                attribute_setter="set_color_temp",
                range_getter="valid_temperature_range",
            )
        )

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        # Color temp is contained in the main device info response.
        return {}

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return valid color-temp range."""
        return ColorTempRange(*self.data.get("color_temp_range"))

    @property
    def color_temp(self):
        """Return current color temperature."""
        return self.data["color_temp"]

    async def set_color_temp(self, temp: int):
        """Set the color temperature."""
        valid_temperature_range = self.valid_temperature_range
        if temp < valid_temperature_range[0] or temp > valid_temperature_range[1]:
            raise ValueError(
                "Temperature should be between {} and {}, was {}".format(
                    *valid_temperature_range, temp
                )
            )

        return await self.call("set_device_info", {"color_temp": temp})
