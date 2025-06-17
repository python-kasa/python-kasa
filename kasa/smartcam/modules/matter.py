"""Implementation of matter module."""

from __future__ import annotations

from ...feature import Feature, FeatureIdentifier
from ..smartcammodule import SmartCamModule


class Matter(SmartCamModule):
    """Implementation of matter module."""

    QUERY_GETTER_NAME = "getMatterSetupInfo"
    QUERY_MODULE_NAME = "matter"
    REQUIRED_COMPONENT = "matter"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id=FeatureIdentifier.MATTER_SETUP_CODE.value,
                name="Matter setup code",
                container=self,
                attribute_getter=lambda x: x.info["setup_code"],
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id=FeatureIdentifier.MATTER_SETUP_PAYLOAD.value,
                name="Matter setup payload",
                container=self,
                attribute_getter=lambda x: x.info["setup_payload"],
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

    @property
    def info(self) -> dict[str, str]:
        """Matter setup info."""
        return self.data
