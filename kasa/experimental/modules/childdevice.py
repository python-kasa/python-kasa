"""Child device module."""

from ..smartcameramodule import SmartCameraModule


class ChildDevice(SmartCameraModule):
    """Implementation for child devices."""

    async def _post_update_hook(self):
        """Perform actions after a device update.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        query = {
            "getChildDeviceList": {"childControl": {"start_index": 0}},
        }
        return query
