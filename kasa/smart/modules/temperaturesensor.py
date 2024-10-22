"""Implementation of temperature module."""

from __future__ import annotations

from typing import Literal

from ...feature import Feature
from ..smartmodule import SmartModule


class TemperatureSensor(SmartModule):
    """Implementation of temperature module."""

    REQUIRED_COMPONENT = "temperature"
    QUERY_GETTER_NAME = "get_comfort_temp_config"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="temperature",
                name="Temperature",
                container=self,
                attribute_getter="temperature",
                icon="mdi:thermometer",
                category=Feature.Category.Primary,
                unit_getter="temperature_unit",
                type=Feature.Type.Sensor,
            )
        )
        if "current_temp_exception" in self._device.sys_info:
            self._add_feature(
                Feature(
                    self._device,
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
                self._device,
                id="temperature_unit",
                name="Temperature unit",
                container=self,
                attribute_getter="temperature_unit",
                attribute_setter="set_temperature_unit",
                type=Feature.Type.Choice,
                choices_getter=lambda: ["celsius", "fahrenheit"],
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def temperature(self) -> float:
        """Return current humidity in percentage."""
        return self._device.sys_info["current_temp"]

    @property
    def temperature_warning(self) -> bool:
        """Return True if temperature is outside of the wanted range."""
        return self._device.sys_info.get("current_temp_exception", 0) != 0

    @property
    def temperature_unit(self) -> Literal["celsius", "fahrenheit"]:
        """Return current temperature unit."""
        return self._device.sys_info["temp_unit"]

    async def set_temperature_unit(
        self, unit: Literal["celsius", "fahrenheit"]
    ) -> dict:
        """Set the device temperature unit."""
        return await self.call("set_temperature_unit", {"temp_unit": unit})
