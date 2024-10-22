"""Implementation of device module."""

from __future__ import annotations

from ...device_type import DeviceType
from ..smartmodule import SmartModule


class DeviceModule(SmartModule):
    """Implementation of device module."""

    REQUIRED_COMPONENT = "device"

    async def _post_update_hook(self):
        """Perform actions after a device update.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        query = {
            "get_device_info": None,
        }
        # Device usage is not available on older firmware versions
        # or child devices of hubs
        if self.supported_version >= 2 and (
            self._device.parent is None
            or self._device.parent.device_type is not DeviceType.Hub
        ):
            query["get_device_usage"] = None

        return query
