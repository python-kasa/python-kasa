"""Implementation of waterleak module."""

from __future__ import annotations

from enum import Enum
from typing import Literal, TypeAlias

from ...feature import Feature
from ..smartmodule import SmartModule


class WaterleakStatus(Enum):
    """Waterleawk status."""

    Normal = "normal"
    LeakDetected = "water_leak"
    Drying = "water_dry"


Volume: TypeAlias = Literal["low", "normal", "high", "mute"]
ALLOWED_VOLUMES = ["low", "normal", "high", "mute"]


class WaterleakSensor(SmartModule):
    """Implementation of waterleak module."""

    REQUIRED_COMPONENT = "sensor_alarm"
    QUERY_GETTER_NAME = "get_alarm_config"

    def _initialize_features(self):
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="water_leak",
                name="Water leak",
                container=self,
                attribute_getter="status",
                icon="mdi:water",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="water_alert",
                name="Water alert",
                container=self,
                attribute_getter="alert",
                icon="mdi:water-alert",
                category=Feature.Category.Primary,
                type=Feature.Type.BinarySensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="water_alert_volume",
                name="Water alert volume",
                container=self,
                attribute_getter="alert_volume",
                attribute_setter="set_alert_volume",
                type=Feature.Type.Choice,
                choices_getter=lambda: ALLOWED_VOLUMES,
            )
        )

    @property
    def status(self) -> WaterleakStatus:
        """Return current humidity in percentage."""
        return WaterleakStatus(self._device.sys_info["water_leak_status"])

    @property
    def alert(self) -> bool:
        """Return true if alarm is active."""
        return self._device.sys_info["in_alarm"]

    @property
    def alert_volume(self) -> Volume:
        """Get water leak alert volume."""
        return self.data["volume"]

    async def set_alert_volume(self, volume: Volume):
        """Set water leak alert volume."""
        await self.call("set_alarm_config", {"volume": volume})
