"""Implementation of cloud module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class Cloud(SmartModule):
    """Implementation of cloud module."""

    QUERY_GETTER_NAME = "get_connect_cloud_state"
    REQUIRED_COMPONENT = "cloud_connect"
    MINIMUM_UPDATE_INTERVAL_SECS = 60

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
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
    def is_connected(self) -> bool:
        """Return True if device is connected to the cloud."""
        if self._has_data_error():
            return False
        return self.data["status"] == 0
