"""Implementation for child device setup.

This module allows pairing and disconnecting child devices.
"""

from __future__ import annotations

import asyncio
import logging

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

    async def get_supported_device_categories(self) -> list[dict]:
        """Get supported device categories."""
        categories = await self.call("get_support_child_device_category")
        return categories["get_support_child_device_category"]["device_category_list"]

    async def pair(self, *, timeout: int = 10) -> list[dict]:
        """Scan for new devices and pair after discovering first new device."""
        await self.call("begin_scanning_child_device")

        _LOGGER.info("Waiting %s seconds for discovering new devices", timeout)
        await asyncio.sleep(timeout)
        detected = await self._get_detected_devices()

        if not detected["child_device_list"]:
            _LOGGER.info("No devices found.")
            return []

        _LOGGER.info(
            "Discovery done, found %s devices: %s",
            len(detected["child_device_list"]),
            detected,
        )

        await self._add_devices(detected)

        return detected["child_device_list"]

    async def unpair(self, device_id: str) -> dict:
        """Remove device from the hub."""
        payload = {"child_device_list": [{"device_id": device_id}]}
        return await self.call("remove_child_device_list", payload)

    async def _add_devices(self, devices: dict) -> dict:
        """Add devices based on get_detected_device response.

        Pass the output from :ref:_get_detected_devices: as a parameter.
        """
        res = await self.call("add_child_device_list", devices)
        return res

    async def _get_detected_devices(self) -> dict:
        """Return list of devices detected during scanning."""
        param = {"scan_list": await self.get_supported_device_categories()}
        res = await self.call("get_scan_child_device_list", param)
        _LOGGER.debug("Scan status: %s", res)
        return res["get_scan_child_device_list"]
