"""Implementation of device module."""
from typing import Dict

from ..smartmodule import SmartModule


class DeviceModule(SmartModule):
    """Implementation of device module."""

    REQUIRED_COMPONENT = "device"

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        query = {
            "get_device_info": None,
        }
        # Device usage is not available on older firmware versions
        if self._device._components[self.REQUIRED_COMPONENT] >= 2:
            query["get_device_usage"] = None

        return query
