"""Implementation for child device setup.

This module allows pairing and disconnecting child devices.
"""

from __future__ import annotations

import asyncio
import logging

# hen support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout

from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class ChildSetupModule(SmartModule):
    """Implementation for child device setup."""

    REQUIRED_COMPONENT = "child_quick_setup"
    QUERY_GETTER_NAME = "get_support_child_device_category"

    @property
    def supported_device_categories(self) -> list[str]:
        """Return supported device categories."""
        return self.data["device_category_list"]

    async def pair(self, *, timeout=5):
        """Scan for new devices and pair after discovering first new device."""
        await self.call("begin_scanning_child_device")

        discovered: dict = {}
        try:
            async with asyncio_timeout(timeout):
                while True:
                    await asyncio.sleep(0.5)
                    res = await self.get_detected_devices()
                    if res["child_device_list"]:
                        discovered = res
                        break

        except TimeoutError:
            pass

        _LOGGER.info(
            "Discovery done, found %s devices", len(discovered["child_device_list"])
        )
        if discovered:
            _LOGGER.info("Adding %s", discovered)
            await self.add_devices(discovered)
        else:
            _LOGGER.warning("No devices found.")

    async def unpair(self, device_id: str):
        """Remove device from the hub."""
        payload = {"child_device_list": [{"device_id": device_id}]}
        return await self._device._query_helper("remove_child_device_list", payload)

    async def add_devices(self, devices: dict):
        """Add devices."""
        return await self._device._query_helper("add_child_device_list", devices)

    async def get_detected_devices(self) -> dict:
        """Return list of devices detected during scanning."""
        param = {"scan_list": self.supported_device_categories}
        res = await self.call("get_scan_child_device_list", param)
        _LOGGER.debug("Scan status: %s", res)
        return res["get_scan_child_device_list"]
