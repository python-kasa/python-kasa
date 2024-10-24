"""Module for child devices."""

from ...device_type import DeviceType
from ..smartcameramodule import SmartCameraModule


class ChildDevice(SmartCameraModule):
    """Implementation for child devices."""

    NAME = "childdevice"
    QUERY_GETTER_NAME = "getChildDeviceList"
    QUERY_MODULE_NAME = "childControl"

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        return {self.QUERY_GETTER_NAME: {self.QUERY_MODULE_NAME: {"start_index": 0}}}

    async def _check_supported(self):
        """Additional check to see if the module is supported by the device."""
        return self._device.device_type is DeviceType.Hub
