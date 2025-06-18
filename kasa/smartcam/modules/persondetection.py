"""Implementation of person detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class PersonDetection(SmartCamModule):
    """Implementation of person detection module."""

    REQUIRED_COMPONENT = "personDetection"

    QUERY_GETTER_NAME = "getPersonDetectionConfig"
    QUERY_MODULE_NAME = "people_detection"
    QUERY_SECTION_NAMES = "detection"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="person_detection",
                name="Person detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the person detection enabled state."""
        return self.data["detection"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the person detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setPersonDetectionConfig", self.QUERY_MODULE_NAME, "detection", params
        )
