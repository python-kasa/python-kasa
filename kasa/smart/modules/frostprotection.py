"""Frost protection module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

# TODO: this may not be necessary with __future__.annotations
if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class FrostProtection(SmartModule):
    """Implementation for frost protection module.

    This basically turns the thermostat on and off.
    """

    REQUIRED_COMPONENT = "frost_protection"
    # TODO: the information required for current features do not require this query
    QUERY_GETTER_NAME = "get_frost_protection"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "frost_protection_enabled",
                name="Frost protection enabled",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
            )
        )

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
