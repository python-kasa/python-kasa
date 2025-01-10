"""Implementation of device module."""

from __future__ import annotations

from ..smartmodule import SmartModule


class DeviceModule(SmartModule):
    """Implementation of device module."""

    REQUIRED_COMPONENT = "device"

    async def _post_update_hook(self) -> None:
        """Perform actions after a device update.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        if self._device._is_hub_child:
            # Child devices get their device info updated by the parent device.
            return {}
        query = {
            "get_device_info": None,
        }
        # Device usage is not available on older firmware versions
        # or child devices of hubs
        if self.supported_version >= 2:
            query["get_device_usage"] = None

        return query
