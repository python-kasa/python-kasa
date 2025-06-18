"""Implementation of tamper detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class TamperDetection(SmartCamModule):
    """Implementation of tamper detection module."""

    REQUIRED_COMPONENT = "tamperDetection"

    QUERY_GETTER_NAME = "getTamperDetectionConfig"
    QUERY_MODULE_NAME = "tamper_detection"
    QUERY_SECTION_NAMES = "tamper_det"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="tamper_detection",
                name="Tamper detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the tamper detection enabled state."""
        return self.data["tamper_det"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the tamper detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setTamperDetectionConfig", self.QUERY_MODULE_NAME, "tamper_det", params
        )
