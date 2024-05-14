"""Implementation of color temp module."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...feature import Feature
from ...interfaces.light import ColorTempRange
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)

DEFAULT_TEMP_RANGE = [2500, 6500]


class ColorTemperature(SmartModule):
    """Implementation of color temp module."""

    REQUIRED_COMPONENT = "color_temperature"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "color_temperature",
                "Color temperature",
                container=self,
                attribute_getter="color_temp",
                attribute_setter="set_color_temp",
                range_getter="valid_temperature_range",
                category=Feature.Category.Primary,
                type=Feature.Type.Number,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Color temp is contained in the main device info response.
        return {}

    @property
    def valid_temperature_range(self) -> ColorTempRange:
        """Return valid color-temp range."""
        if (ct_range := self.data.get("color_temp_range")) is None:
            _LOGGER.debug(
                "Device doesn't report color temperature range, "
                "falling back to default %s",
                DEFAULT_TEMP_RANGE,
            )
            ct_range = DEFAULT_TEMP_RANGE
        return ColorTempRange(*ct_range)

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

    async def _check_supported(self) -> bool:
        """Check the color_temp_range has more than one value."""
        return self.valid_temperature_range.min != self.valid_temperature_range.max
