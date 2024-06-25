"""Frost protection module."""

from __future__ import annotations

from ..smartmodule import SmartModule


class FrostProtection(SmartModule):
    """Implementation for frost protection module.

    This basically turns the thermostat on and off.
    """

    REQUIRED_COMPONENT = "frost_protection"
    QUERY_GETTER_NAME = "get_frost_protection"

    @property
    def enabled(self) -> bool:
        """Return True if frost protection is on."""
        return self._device.sys_info["frost_protection_on"]

    async def set_enabled(self, enable: bool):
        """Enable/disable frost protection."""
        return await self.call(
            "set_device_info",
            {"frost_protection_on": enable},
        )

    @property
    def minimum_temperature(self) -> int:
        """Return frost protection minimum temperature."""
        return self.data["min_temp"]

    @property
    def temperature_unit(self) -> str:
        """Return frost protection temperature unit."""
        return self.data["temp_unit"]
