"""Implementation of contact sensor module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class ContactSensor(SmartModule):
    """Implementation of contact sensor module."""

    REQUIRED_COMPONENT = None  # we depend on availability of key
    SYSINFO_LOOKUP_KEYS = ["open"]

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="is_open",
                name="Open",
                container=self,
                attribute_getter="is_open",
                icon="mdi:door",
                category=Feature.Category.Primary,
                type=Feature.Type.BinarySensor,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def is_open(self) -> bool:
        """Return True if the contact sensor is open."""
        return self._device.sys_info["open"]
