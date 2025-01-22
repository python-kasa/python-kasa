"""Implementation of pet detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class PetDetection(SmartCamModule):
    """Implementation of pet detection module."""

    REQUIRED_COMPONENT = "petDetection"

    QUERY_GETTER_NAME = "getPetDetectionConfig"
    QUERY_MODULE_NAME = "pet_detection"
    QUERY_SECTION_NAMES = "detection"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="pet_detection",
                name="Pet detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the pet detection enabled state."""
        return self.data["detection"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the pet detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setPetDetectionConfig", self.QUERY_MODULE_NAME, "detection", params
        )
