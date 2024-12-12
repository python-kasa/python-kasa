"""Implementation of matter module.

Only function is to indicate matter Support
"""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class Matter(SmartModule):
    """Implementation of matter module.

    Currently only adds a feature to indicate the device supports matter.
    """

    REQUIRED_COMPONENT = "matter"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="matter_device",
                name="Matter device",
                container=self,
                attribute_getter=lambda _: True,
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )
