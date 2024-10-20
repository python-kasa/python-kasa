"""Implementation of device module."""

from __future__ import annotations

from ..smartcameramodule import SmartCameraModule


class DeviceModule(SmartCameraModule):
    """Implementation of device module."""

    async def _post_update_hook(self):
        """Perform actions after a device update.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        query = {
            "getDeviceInfo": {"device_info": {"name": ["basic_info", "info"]}},
        }
        return query
