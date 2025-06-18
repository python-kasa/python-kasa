"""Implementation of baby cry detection module."""

from __future__ import annotations

import logging

from ...feature import Feature
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class BabyCryDetection(SmartCamModule):
    """Implementation of baby cry detection module."""

    REQUIRED_COMPONENT = "babyCryDetection"

    QUERY_GETTER_NAME = "getBCDConfig"
    QUERY_MODULE_NAME = "sound_detection"
    QUERY_SECTION_NAMES = "bcd"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="baby_cry_detection",
                name="Baby cry detection",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return the baby cry detection enabled state."""
        return self.data["bcd"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the baby cry detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setBCDConfig", self.QUERY_MODULE_NAME, "bcd", params
        )
