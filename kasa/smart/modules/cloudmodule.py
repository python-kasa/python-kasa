"""Implementation of cloud module."""
from typing import TYPE_CHECKING

from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class CloudModule(SmartModule):
    """Implementation of cloud module."""

    QUERY_GETTER_NAME = "get_connect_cloud_state"
    REQUIRED_COMPONENT = "cloud_connect"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)

        self._add_feature(
            Feature(
                device,
                "Cloud connection",
                container=self,
                attribute_getter="is_connected",
                icon="mdi:cloud",
                type=FeatureType.BinarySensor,
            )
        )

    @property
    def is_connected(self):
        """Return True if device is connected to the cloud."""
        return self.data["status"] == 0
