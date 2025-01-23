"""Module for child devices."""

from ...device_type import DeviceType
from ..smartcammodule import SmartCamModule


class ChildDevice(SmartCamModule):
    """Implementation for child devices."""

    REQUIRED_COMPONENT = "childControl"
    NAME = "childdevice"
    QUERY_GETTER_NAME = "getChildDeviceList"
    # This module is unusual in that QUERY_MODULE_NAME in the response is not
    # the same one used in the request.
    QUERY_MODULE_NAME = "child_device_list"

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        q = {self.QUERY_GETTER_NAME: {"childControl": {"start_index": 0}}}
        if self._device.device_type is DeviceType.Hub:
            q["getChildDeviceComponentList"] = {"childControl": {"start_index": 0}}
        return q

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return self._device.device_type is DeviceType.Hub
