"""Implementation of glass detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class GlassDetection(SmartCamModule):
    """Implementation of glass detection module."""

    REQUIRED_COMPONENT = "glassDetection"

    QUERY_GETTER_NAME = "getGlassDetectionConfig"
    QUERY_MODULE_NAME = "glass_detection"
    QUERY_SECTION_NAMES = "detection"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id=self.QUERY_MODULE_NAME,
                name="Glass detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the glass detection enabled state."""
        return self.data[self.QUERY_SECTION_NAMES]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the glass detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setGlassDetectionConfig", self.QUERY_MODULE_NAME, self.QUERY_SECTION_NAMES, params
        )
