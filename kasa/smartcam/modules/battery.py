"""Implementation of smartcam battery module."""

from __future__ import annotations

import logging
from typing import Any

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

        # Optional on some battery cameras (e.g., C460).
        if self._optional_float_sysinfo("battery_temperature") is not None:
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

        if self._optional_float_sysinfo("battery_voltage") is not None:
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

    def _optional_float_sysinfo(self, key: str) -> float | None:
        """Return sys_info[key] as float, or None if not available or invalid."""
        v_any: Any = self._device.sys_info.get(key)
        if v_any in (None, "NO"):
            return None

        try:
            # Accept ints/floats and numeric strings.
            return float(v_any)
        except (TypeError, ValueError):
            return None

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
    def battery_temperature(self) -> float | None:
        """Return battery temperature in °C (if available)."""
        return self._optional_float_sysinfo("battery_temperature")

    @property
    def battery_voltage(self) -> float | None:
        """Return battery voltage in V (if available)."""
        v = self._optional_float_sysinfo("battery_voltage")
        return None if v is None else v / 1_000

    @property
    def battery_charging(self) -> bool:
        """Return True if battery is charging."""
        v = self._device.sys_info.get("battery_charging")
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("yes", "true", "1", "charging", "on")
