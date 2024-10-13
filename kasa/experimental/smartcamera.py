"""Module for smartcamera."""

from ..smart import SmartDevice


class SmartCamera(SmartDevice):
    """Class for smart cameras."""

    async def update(self, update_children: bool = False):
        """Update the device."""
        initial_query = {
            "getDeviceInfo": {"device_info": {"name": ["basic_info"]}},
        }
        resp = await self.protocol.query(initial_query)
        self._last_update.update(resp)
        info = self._try_get_response(resp, "getDeviceInfo")
        self._info = info["device_info"]["basic_info"]
        pass
