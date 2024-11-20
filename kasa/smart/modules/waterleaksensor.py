"""Implementation of waterleak module."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from ...feature import Feature
from ..smartmodule import Module, SmartModule


class WaterleakStatus(Enum):
    """Waterleawk status."""

    Normal = "normal"
    LeakDetected = "water_leak"
    Drying = "water_dry"


class WaterleakSensor(SmartModule):
    """Implementation of waterleak module."""

    REQUIRED_COMPONENT = "sensor_alarm"

    def _initialize_features(self) -> None:
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
                id="water_alert_timestamp",
                name="Last alert timestamp",
                container=self,
                attribute_getter="alert_timestamp",
                icon="mdi:alert",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
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

    @property
    def alert_timestamp(self) -> datetime | None:
        """Return timestamp of the last leak trigger."""
        # The key is not always be there, maybe if it hasn't ever been triggered?
        if "trigger_timestamp" not in self._device.sys_info:
            return None

        ts = self._device.sys_info["trigger_timestamp"]
        tz = self._device.modules[Module.Time].timezone
        return datetime.fromtimestamp(ts, tz=tz)
