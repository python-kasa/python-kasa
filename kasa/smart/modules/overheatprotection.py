"""Overheat module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class OverheatProtection(SmartModule):
    """Implementation for overheat_protection."""

    SYSINFO_LOOKUP_KEYS = ["overheated", "overheat_status"]

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                container=self,
                id="overheated",
                name="Overheated",
                attribute_getter="overheated",
                icon="mdi:heat-wave",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Info,
            )
        )

    @property
    def overheated(self) -> bool:
        """Return True if device reports overheating."""
        if (value := self._device.sys_info.get("overheat_status")) is not None:
            # Value can be normal, cooldown, or overheated.
            # We report all but normal as overheated.
            return value != "normal"

        return self._device.sys_info["overheated"]

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}
