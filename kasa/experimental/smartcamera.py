"""Module for smartcamera."""

from __future__ import annotations

from ..device_type import DeviceType
from ..smart import SmartDevice
from .sslaestransport import SmartErrorCode


class SmartCamera(SmartDevice):
    """Class for smart cameras."""

    async def update(self, update_children: bool = False):
        """Update the device."""
        initial_query = {
            "getDeviceInfo": {"device_info": {"name": ["basic_info", "info"]}},
            "getLensMaskConfig": {"lens_mask": {"name": ["lens_mask_info"]}},
        }
        resp = await self.protocol.query(initial_query)
        self._last_update.update(resp)
        info = self._try_get_response(resp, "getDeviceInfo")
        self._info = self._map_info(info["device_info"])
        self._last_update = resp

    def _map_info(self, device_info: dict) -> dict:
        basic_info = device_info["basic_info"]
        return {
            "model": basic_info["device_model"],
            "type": basic_info["device_type"],
            "alias": basic_info["device_alias"],
            "fw_ver": basic_info["sw_version"],
            "hw_ver": basic_info["hw_version"],
            "mac": basic_info["mac"],
            "hwId": basic_info["hw_id"],
            "oem_id": basic_info["oem_id"],
        }

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        if isinstance(self._last_update["getLensMaskConfig"], SmartErrorCode):
            return True
        return (
            self._last_update["getLensMaskConfig"]["lens_mask"]["lens_mask_info"][
                "enabled"
            ]
            == "on"
        )

    async def set_state(self, on: bool):
        """Set the device state."""
        if isinstance(self._last_update["getLensMaskConfig"], SmartErrorCode):
            return
        query = {
            "setLensMaskConfig": {
                "lens_mask": {"lens_mask_info": {"enabled": "on" if on else "off"}}
            },
        }
        return await self.protocol.query(query)

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return DeviceType.Camera

    @property
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""
        if self._info:
            return self._info.get("alias")
        return None

    @property
    def hw_info(self) -> dict:
        """Return hardware info for the device."""
        return {
            "sw_ver": self._info.get("hw_ver"),
            "hw_ver": self._info.get("fw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("hwId"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }
