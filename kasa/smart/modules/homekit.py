"""Implementation of homekit module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class HomeKit(SmartModule):
    """Implementation of homekit module."""

    QUERY_GETTER_NAME: str = "get_homekit_info"
    REQUIRED_COMPONENT = "homekit"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="homekit_setup_code",
                name="Homekit setup code",
                container=self,
                attribute_getter=lambda x: x.info["mfi_setup_code"],
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )

    @property
    def info(self) -> dict[str, str]:
        """Homekit mfi setup info."""
        return self.data
