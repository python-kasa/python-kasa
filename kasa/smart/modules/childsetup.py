"""Implementation for child device setup.

This module allows pairing and disconnecting child devices.
"""

from __future__ import annotations

import asyncio
import logging

from ...feature import Feature
from ...interfaces.childsetup import ChildSetup as ChildSetupInterface
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class ChildSetup(SmartModule, ChildSetupInterface):
    """Implementation for child device setup."""

    REQUIRED_COMPONENT = "child_quick_setup"
    QUERY_GETTER_NAME = "get_support_child_device_category"
    _categories: list[str] = []

    # Supported child device categories will hardly ever change
    MINIMUM_UPDATE_INTERVAL_SECS = 60 * 60 * 24

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

    async def _post_update_hook(self) -> None:
        self._categories = [
            cat["category"] for cat in self.data["device_category_list"]
        ]

    @property
    def supported_categories(self) -> list[str]:
        """Supported child device categories."""
        return self._categories

    async def pair(self, *, timeout: int = 10) -> list[dict]:
        """Scan for new devices and pair them."""
        await self.call("begin_scanning_child_device")

        _LOGGER.info("Waiting %s seconds for discovering new devices", timeout)
        await asyncio.sleep(timeout)
        detected = await self._get_detected_devices()

        if not detected["child_device_list"]:
            _LOGGER.warning(
                "No devices found, make sure to activate pairing "
                "mode on the devices to be added."
            )
            return []

        _LOGGER.info(
            "Discovery done, found %s devices: %s",
            len(detected["child_device_list"]),
            detected,
        )

        return await self._add_devices(detected)

    async def unpair(self, device_id: str) -> dict:
        """Remove device from the hub."""
        _LOGGER.info("Going to unpair %s from %s", device_id, self)

        payload = {"child_device_list": [{"device_id": device_id}]}
        res = await self.call("remove_child_device_list", payload)
        await self._device.update()
        return res

    async def _add_devices(self, devices: dict) -> list[dict]:
        """Add devices based on get_detected_device response.

        Pass the output from :ref:_get_detected_devices: as a parameter.
        """
        await self.call("add_child_device_list", devices)

        await self._device.update()

        successes = []
        for detected in devices["child_device_list"]:
            device_id = detected["device_id"]

            result = "not added"
            if device_id in self._device._children:
                result = "added"
                successes.append(detected)

            msg = f"{detected['device_model']} - {device_id} - {result}"
            _LOGGER.info("Added child to %s: %s", self._device.host, msg)

        return successes

    async def _get_detected_devices(self) -> dict:
        """Return list of devices detected during scanning."""
        param = {"scan_list": self.data["device_category_list"]}
        res = await self.call("get_scan_child_device_list", param)
        _LOGGER.debug("Scan status: %s", res)
        return res["get_scan_child_device_list"]
