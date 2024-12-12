"""Implementation of homekit module.

Only function is to indicate homekit Support
"""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class HomeKit(SmartModule):
    """Implementation of homekit module.

    Currently only adds a feature to indicate the device supports homekit.
    """

    REQUIRED_COMPONENT = "homekit"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="homekit_device",
                name="Homekit device",
                container=self,
                attribute_getter=lambda _: True,
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Debug,
            )
        )
