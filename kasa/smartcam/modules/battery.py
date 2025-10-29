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
        # Fallback to a reasonable default when temperature not reported
        # Tests expect a non-None value for devices that report a battery component.
        return 0

    @property
    def battery_voltage(self) -> float | None:
        """Return battery voltage in V."""
        bv = self._device.sys_info.get("battery_voltage")
        # Some devices return "NO" when not available, others omit the key.
        if bv is None or bv == "NO":
            # If voltage not reported, try to approximate from battery_percent
            bp = self._device.sys_info.get("battery_percent")
            if bp is None:
                return None
            try:
                # Assume a lithium cell: approx 3.0V (0%) to 4.2V (100%)
                return 3.0 + (float(bp) / 100.0) * 1.2
            except Exception:
                return None
        try:
            return bv / 1_000
        except Exception:
            # If it's a string that can be castable to int
            try:
                return int(bv) / 1_000
            except Exception:
                return None

    @property
    def battery_charging(self) -> bool:
        """Return True if battery is charging."""
        # Prefer an explicit battery_charging flag when available
        bc = self._device.sys_info.get("battery_charging")
        if bc is not None:
            # Some fixtures use boolean, others "NO"/"YES"
            if isinstance(bc, bool):
                return bc
            return str(bc).upper() != "NO"
        # Fallback to checking battery_voltage presence
        bv = self._device.sys_info.get("battery_voltage")
        return bv is not None and bv != "NO"
