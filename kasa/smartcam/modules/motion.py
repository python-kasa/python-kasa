"""Implementation of motion detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class Motion(SmartCamModule):
    """Implementation of lens mask module."""

    REQUIRED_COMPONENT = "detection"

    QUERY_GETTER_NAME = "getDetectionConfig"
    QUERY_MODULE_NAME = "motion_detection"
    QUERY_SECTION_NAMES = "motion_det"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="motion_detection_enabled",
                name="Motion detection enabled",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Primary,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the lens mask state."""
        return self.data["motion_det"]["enabled"] == "on"

    async def set_enabled(self, state: bool) -> dict:
        """Set the lens mask state."""
        params = {"enabled": "on" if state else "off"}
        return await self._device._query_setter_helper(
            "setLensMaskConfig", self.QUERY_MODULE_NAME, "motion_det", params
        )
