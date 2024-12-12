"""Implementation of matter module.

Only function is to indicate matter Support
"""

from __future__ import annotations

from ...feature import Feature
from ..smartcammodule import SmartCamModule


class Matter(SmartCamModule):
    """Implementation of matter module.

    Currently only adds a feature to indicate the device supports matter.
    """

    NAME = "SmartMatter"
    QUERY_GETTER_NAME = "getMatterSetupInfo"
    QUERY_MODULE_NAME = "matter"
    REQUIRED_COMPONENT = "matter"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="matter_setup_code",
                name="Matter setup code",
                container=self,
                attribute_getter=lambda x: x.info["setup_code"],
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

    @property
    def info(self) -> dict[str, str]:
        """Matter setup info."""
        return self.data
