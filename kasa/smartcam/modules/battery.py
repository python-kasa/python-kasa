"""Implementation of baby cry detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class Battery(SmartCamModule):
    """Implementation of a battery module."""

    REQUIRED_COMPONENT = "battery"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                "battery_low",
                "Battery low",
                container=self,
                attribute_getter="battery_low",
                icon="mdi:alert",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                "battery_level",
                "Battery level",
                container=self,
                attribute_getter="battery_percent",
                icon="mdi:battery",
                unit_getter=lambda: "%",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                "battery_temperature",
                "Battery temperature",
                container=self,
                attribute_getter="battery_temperature",
                icon="mdi:battery",
                unit_getter=lambda: "celsius",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "battery_voltage",
                "Battery voltage",
                container=self,
                attribute_getter="battery_voltage",
                icon="mdi:battery",
                unit_getter=lambda: "V",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "battery_charging",
                "Battery charging",
                container=self,
                attribute_getter="battery_charging",
                icon="mdi:alert",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def battery_percent(self) -> int:
        """Return battery level."""
        return self._device.sys_info["battery_percent"]

    @property
    def battery_low(self) -> bool:
        """Return True if battery is low."""
        return self._device.sys_info["low_battery"]

    @property
    def battery_temperature(self) -> bool:
        """Return battery voltage in C."""
        return self._device.sys_info["battery_temperature"]

    @property
    def battery_voltage(self) -> bool:
        """Return battery voltage in V."""
        return self._device.sys_info["battery_voltage"] / 1_000

    @property
    def battery_charging(self) -> bool:
        """Return True if battery is charging."""
        return self._device.sys_info["battery_voltage"] != "NO"
