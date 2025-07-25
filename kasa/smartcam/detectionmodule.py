"""SmartCamModule base class for all detections."""

from __future__ import annotations

import logging

from kasa.feature import Feature
from kasa.smart.smartmodule import allow_update_after
from kasa.smartcam.smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class DetectionModule(SmartCamModule):
    """SmartCamModule base class for all detections."""

    DETECTION_FEATURE_ID: str = ""
    DETECTION_FEATURE_NAME: str = ""
    QUERY_SETTER_NAME: str = ""
    QUERY_SET_SECTION_NAME: str = ""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id=self.DETECTION_FEATURE_ID,
                name=self.DETECTION_FEATURE_NAME,
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
        return self.data[self.QUERY_SECTION_NAMES]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the baby cry detection enabled state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            self.QUERY_SETTER_NAME,
            self.QUERY_MODULE_NAME,
            self.QUERY_SET_SECTION_NAME,
            params,
        )
