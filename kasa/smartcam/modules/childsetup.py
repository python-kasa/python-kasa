"""Implementation for child device setup.

This module allows pairing and disconnecting child devices.
"""

from __future__ import annotations

import asyncio
import logging

from ...feature import Feature
from ...interfaces.childsetup import ChildSetup as ChildSetupInterface
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class ChildSetup(SmartCamModule, ChildSetupInterface):
    """Implementation for child device setup."""

    REQUIRED_COMPONENT = "childQuickSetup"
    QUERY_GETTER_NAME = "getSupportChildDeviceCategory"
    QUERY_MODULE_NAME = "childControl"
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
            cat["category"].replace("ipcamera", "camera")
            for cat in self.data["device_category_list"]
        ]

    @property
    def supported_categories(self) -> list[str]:
        """Supported child device categories."""
        return self._categories

    async def pair(self, *, timeout: int = 10) -> list[dict]:
        """Scan for new devices and pair them."""
        await self.call(
            "startScanChildDevice", {"childControl": {"category": self._categories}}
        )

        _LOGGER.info("Waiting %s seconds for discovering new devices", timeout)

        await asyncio.sleep(timeout)
        res = await self.call(
            "getScanChildDeviceList", {"childControl": {"category": self._categories}}
        )

        detected_list = res["getScanChildDeviceList"]["child_device_list"]
        if not detected_list:
            _LOGGER.warning(
                "No devices found, make sure to activate pairing "
                "mode on the devices to be added."
            )
            return []

        _LOGGER.info(
            "Discovery done, found %s devices: %s",
            len(detected_list),
            detected_list,
        )
        return await self._add_devices(detected_list)

    async def _add_devices(self, detected_list: list[dict]) -> list[dict]:
        """Add devices based on getScanChildDeviceList response."""
        await self.call(
            "addScanChildDeviceList",
            {"childControl": {"child_device_list": detected_list}},
        )

        await self._device.update()

        successes = []
        for detected in detected_list:
            device_id = detected["device_id"]

            result = "not added"
            if device_id in self._device._children:
                result = "added"
                successes.append(detected)

            msg = f"{detected['device_model']} - {device_id} - {result}"
            _LOGGER.info("Adding child to %s: %s", self._device.host, msg)

        return successes

    async def unpair(self, device_id: str) -> dict:
        """Remove device from the hub."""
        _LOGGER.info("Going to unpair %s from %s", device_id, self)

        payload = {"childControl": {"child_device_list": [{"device_id": device_id}]}}
        res = await self.call("removeChildDeviceList", payload)
        await self._device.update()
        return res
