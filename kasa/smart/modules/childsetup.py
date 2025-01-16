"""Implementation for child device setup.

This module allows pairing and disconnecting child devices.
"""

from __future__ import annotations

import asyncio
import logging
from asyncio import timeout as asyncio_timeout

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class ChildSetup(SmartModule):
    """Implementation for child device setup."""

    REQUIRED_COMPONENT = "child_quick_setup"
    QUERY_GETTER_NAME = "get_support_child_device_category"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="pair",
                name="Pair",
                container=self,
                attribute_setter="pair",
                category=Feature.Category.Config,
                type=Feature.Type.Action,
            )
        )

    @property
    def supported_device_categories(self) -> list[str]:
        """Return supported device categories."""
        return self.data["device_category_list"]

    async def pair(self, *, timeout: int = 10) -> dict:
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

        if not discovered:
            _LOGGER.warning("No devices found.")
            return {}

        _LOGGER.info(
            "Discovery done, found %s devices", len(discovered["child_device_list"])
        )

        return await self.add_devices(discovered)

    async def unpair(self, device_id: str) -> dict:
        """Remove device from the hub."""
        payload = {"child_device_list": [{"device_id": device_id}]}
        return await self.call("remove_child_device_list", payload)

    async def add_devices(self, devices: dict) -> dict:
        """Add devices."""
        return await self.call("add_child_device_list", devices)

    async def get_detected_devices(self) -> dict:
        """Return list of devices detected during scanning."""
        param = {"scan_list": self.supported_device_categories}
        res = await self.call("get_scan_child_device_list", param)
        _LOGGER.debug("Scan status: %s", res)
        return res["get_scan_child_device_list"]
