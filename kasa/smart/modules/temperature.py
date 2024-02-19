"""Implementation of temperature module."""
from typing import TYPE_CHECKING, Literal

from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class TemperatureSensor(SmartModule):
    """Implementation of temperature module."""

    REQUIRED_COMPONENT = "humidity"
    QUERY_GETTER_NAME = "get_comfort_temp_config"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Temperature",
                container=self,
                attribute_getter="temperature",
                icon="mdi:thermometer",
            )
        )
        self._add_feature(
            Feature(
                device,
                "Temperature warning",
                container=self,
                attribute_getter="temperature_warning",
                type=FeatureType.BinarySensor,
                icon="mdi:alert",
            )
        )
        # TODO: use temperature_unit for feature creation

    @property
    def temperature(self):
        """Return current humidity in percentage."""
        return self._device.sys_info["current_temp"]

    @property
    def temperature_warning(self) -> bool:
        """Return True if humidity is outside of the wanted range."""
        return self._device.sys_info["current_temp_exception"] != 0

    @property
    def temperature_unit(self):
        """Return current temperature unit."""
        return self._device.sys_info["temp_unit"]

    async def set_temperature_unit(self, unit: Literal["celsius", "fahrenheit"]):
        """Set the device temperature unit."""
        return await self.call("set_temperature_unit", {"temp_unit": unit})
