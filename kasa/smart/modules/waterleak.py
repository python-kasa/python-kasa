"""Implementation of waterleak module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class WaterleakSensor(SmartModule):
    """Implementation of waterleak module."""

    # TODO: just a guess, we need a fixture file for this
    REQUIRED_COMPONENT = "waterleak"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Status",
                container=self,
                attribute_getter="status",
                icon="mdi:water",
            )
        )
        self._add_feature(
            Feature(
                device,
                "Alarm",
                container=self,
                attribute_getter="active",
                icon="mdi:water-alert",
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Water leak information is contained in the main device info response.
        return {}

    @property
    def status(self):
        """Return current humidity in percentage."""
        return self._device.sys_info["water_leak_status"]

    @property
    def active(self) -> bool:
        """Return true if alarm is active."""
        return self._device.sys_info["in_alarm"]
