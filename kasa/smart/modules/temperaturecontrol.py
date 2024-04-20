"""Implementation of temperature module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class TemperatureControl(SmartModule):
    """Implementation of temperature module."""

    REQUIRED_COMPONENT = "temperature_control"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Target temperature",
                container=self,
                attribute_getter="target_temperature",
                attribute_setter="set_target_temperature",
                icon="mdi:thermometer",
            )
        )
        # TODO: this might belong into its own module, temperature_correction?
        self._add_feature(
            Feature(
                device,
                "Temperature offset",
                container=self,
                attribute_getter="temperature_offset",
                attribute_setter="set_temperature_offset",
                minimum_value=-10,
                maximum_value=10,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Target temperature is contained in the main device info response.
        return {}

    @property
    def minimum_target_temperature(self) -> int:
        """Minimum available target temperature."""
        return self._device.sys_info["min_control_temp"]

    @property
    def maximum_target_temperature(self) -> int:
        """Minimum available target temperature."""
        return self._device.sys_info["max_control_temp"]

    @property
    def target_temperature(self) -> int:
        """Return target temperature."""
        return self._device.sys_info["target_temperature"]

    async def set_target_temperature(self, target: int):
        """Set target temperature."""
        if (
            target < self.minimum_target_temperature
            or target > self.maximum_target_temperature
        ):
            raise ValueError(
                f"Invalid target temperature {target}, must be in range "
                f"[{self.minimum_target_temperature},{self.maximum_target_temperature}]"
            )

        return await self.call("set_device_info", {"target_temp": target})

    @property
    def temperature_offset(self) -> int:
        """Return temperature offset."""
        return self._device.sys_info["temp_offset"]

    async def set_temperature_offset(self, offset: int):
        """Set temperature offset."""
        if offset < -10 or offset > 10:
            raise ValueError("Temperature offset must be [-10, 10]")

        return await self.call("set_device_info", {"temp_offset": offset})
