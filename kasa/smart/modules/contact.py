"""Implementation of contact sensor module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class ContactSensor(SmartModule):
    """Implementation of contact sensor module."""

    REQUIRED_COMPONENT = "contact"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Open",
                container=self,
                attribute_getter="is_open",
                icon="mdi:door",
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    @property
    def is_open(self):
        """Return True if the contact sensor is open."""
        return self._device.sys_info["open"]
