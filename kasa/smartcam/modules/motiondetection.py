"""Implementation of motion detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class MotionDetection(SmartCamModule):
    """Implementation of motion detection module."""

    REQUIRED_COMPONENT = "detection"

    QUERY_GETTER_NAME = "getDetectionConfig"
    QUERY_MODULE_NAME = "motion_detection"
    QUERY_SECTION_NAMES = "motion_det"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="motion_detection",
                name="Motion detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the motion detection enabled state."""
        return self.data["motion_det"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the motion detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setDetectionConfig", self.QUERY_MODULE_NAME, "motion_det", params
        )
