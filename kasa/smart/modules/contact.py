"""Implementation of contact sensor module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class ContactSensor(SmartModule):
    """Implementation of contact sensor module."""

    REQUIRED_COMPONENT = None  # we depend on availability of key
    REQUIRED_KEY_ON_PARENT = "open"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
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
    def is_open(self):
        """Return True if the contact sensor is open."""
        return self._device.sys_info["open"]
