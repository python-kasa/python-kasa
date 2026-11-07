"""Hub child enumeration via ``getChildDeviceList``.

python-kasa builds :attr:`~kasa.Device.children` from this module's query
response, not from ``getDeviceInfo.child_num``. On some hubs (notably Tapo H500)
those values disagree: ``child_num`` may report paired children while
``getChildDeviceList`` returns ``sum: 0`` and an empty or omitted
``child_device_list`` over LAN. There is no documented LAN "reason" field for
that mismatch — see :ref:`topics-hub-children` in the documentation.
"""

from ...device_type import DeviceType
from ..smartcammodule import SmartCamModule


class ChildDevice(SmartCamModule):
    """Enumerate children paired to a Tapo/Kasa hub.

    Queries ``getChildDeviceList`` (and ``getChildDeviceComponentList`` on hubs)
    during :meth:`~kasa.Device.update()`. The list response is authoritative for
    :attr:`~kasa.Device.children`; ``child_num`` in device info is informational
    only and can disagree — see :ref:`topics-hub-children`.
    """

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
