"""Implementation of waterleak module."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class WaterleakStatus(Enum):
    """Waterleawk status."""

    Normal = "normal"
    LeakDetected = "water_leak"
    Drying = "water_dry"


class WaterleakSensor(SmartModule):
    """Implementation of waterleak module."""

    REQUIRED_COMPONENT = "sensor_alarm"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="water_leak",
                name="Water leak",
                container=self,
                attribute_getter="status",
                icon="mdi:water",
                category=Feature.Category.Debug,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="water_alert",
                name="Water alert",
                container=self,
                attribute_getter="alert",
                icon="mdi:water-alert",
                category=Feature.Category.Primary,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Water leak information is contained in the main device info response.
        return {}

    @property
    def status(self) -> WaterleakStatus:
        """Return current humidity in percentage."""
        return WaterleakStatus(self._device.sys_info["water_leak_status"])

    @property
    def alert(self) -> bool:
        """Return true if alarm is active."""
        return self._device.sys_info["in_alarm"]
