"""Implementation of battery module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class BatterySensor(SmartModule):
    """Implementation of battery module."""

    REQUIRED_COMPONENT = "battery_detect"
    QUERY_GETTER_NAME = "get_battery_detect_info"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "battery_level",
                "Battery level",
                container=self,
                attribute_getter="battery",
                icon="mdi:battery",
                unit="%",
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                "battery_low",
                "Battery low",
                container=self,
                attribute_getter="battery_low",
                icon="mdi:alert",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )

    @property
    def battery(self):
        """Return battery level."""
        return self._device.sys_info["battery_percentage"]

    @property
    def battery_low(self):
        """Return True if battery is low."""
        return self._device.sys_info["at_low_battery"]
