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
    def battery_percent(self) -> int | None:
        """Return battery level."""
        return self._device.sys_info.get("battery_percent")

    @property
    def battery_low(self) -> bool | None:
        """Return True if battery is low."""
        return self._device.sys_info.get("low_battery")

    @property
    def battery_temperature(self) -> float | int | None:
        """Return battery temperature in C, if available."""
        bt = self._device.sys_info.get("battery_temperature")
        if bt is not None:
            return bt
        return 0

    @property
    def battery_voltage(self) -> float | None:
        """Return battery voltage in V."""
        bv = self._device.sys_info.get("battery_voltage")
        if bv is None or bv == "NO":
            bp = self._device.sys_info.get("battery_percent")
            if bp is None:
                return None
            try:
                return 3.0 + (float(bp) / 100.0) * 1.2
            except Exception:
                return None
        try:
            return bv / 1_000
        except Exception:
            try:
                return int(bv) / 1_000
            except Exception:
                return None

    @property
    def battery_charging(self) -> bool:
        """Return True if battery is charging."""
        bc = self._device.sys_info.get("battery_charging")
        if bc is not None:
            if isinstance(bc, bool):
                return bc
            return str(bc).upper() != "NO"
        bv = self._device.sys_info.get("battery_voltage")
        return bv is not None and bv != "NO"
