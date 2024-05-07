"""Implementation of temperature module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class TemperatureSensor(SmartModule):
    """Implementation of temperature module."""

    REQUIRED_COMPONENT = "temperature"
    QUERY_GETTER_NAME = "get_comfort_temp_config"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="temperature",
                name="Temperature",
                container=self,
                attribute_getter="temperature",
                icon="mdi:thermometer",
                category=Feature.Category.Primary,
            )
        )
        if "current_temp_exception" in device.sys_info:
            self._add_feature(
                Feature(
                    device,
                    id="temperature_warning",
                    name="Temperature warning",
                    container=self,
                    attribute_getter="temperature_warning",
                    type=Feature.Type.BinarySensor,
                    icon="mdi:alert",
                    category=Feature.Category.Debug,
                )
            )
        self._add_feature(
            Feature(
                device,
                id="temperature_unit",
                name="Temperature unit",
                container=self,
                attribute_getter="temperature_unit",
                attribute_setter="set_temperature_unit",
                type=Feature.Type.Choice,
                choices=["celsius", "fahrenheit"],
            )
        )
        # TODO: use temperature_unit for feature creation

    @property
    def temperature(self):
        """Return current humidity in percentage."""
        return self._device.sys_info["current_temp"]

    @property
    def temperature_warning(self) -> bool:
        """Return True if temperature is outside of the wanted range."""
        return self._device.sys_info.get("current_temp_exception", 0) != 0

    @property
    def temperature_unit(self):
        """Return current temperature unit."""
        return self._device.sys_info["temp_unit"]

    async def set_temperature_unit(self, unit: Literal["celsius", "fahrenheit"]):
        """Set the device temperature unit."""
        return await self.call("set_temperature_unit", {"temp_unit": unit})
