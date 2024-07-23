"""Implementation of cloud module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class Cloud(SmartModule):
    """Implementation of cloud module."""

    QUERY_GETTER_NAME = "get_connect_cloud_state"
    REQUIRED_COMPONENT = "cloud_connect"
    MINIMUM_UPDATE_INTERVAL_SECS = 60

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)

        self._add_feature(
            Feature(
                device,
                id="cloud_connection",
                name="Cloud connection",
                container=self,
                attribute_getter="is_connected",
                icon="mdi:cloud",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Info,
            )
        )

    @property
    def is_connected(self):
        """Return True if device is connected to the cloud."""
        if self._has_data_error():
            return False
        return self.data["status"] == 0
