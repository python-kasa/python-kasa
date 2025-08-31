"""Implementation of HomeKit module for IOT devices that natively support HomeKit."""

from __future__ import annotations

from typing import Any

from ...feature import Feature
from ..iotmodule import IotModule


class HomeKit(IotModule):
    """Implementation of HomeKit module for IOT devices."""

    def query(self) -> dict:
        """Request HomeKit setup info."""
        return {"smartlife.iot.homekit": {"setup_info_get": {}}}

    @property
    def info(self) -> dict[str, Any]:
        """Return the HomeKit setup info."""
        return self.data["setup_info_get"]

    @property
    def setup_code(self) -> str:
        """Return the HomeKit setup code."""
        return self.info["setup_code"]

    @property
    def setup_payload(self) -> str:
        """Return the HomeKit setup payload."""
        return self.info["setup_payload"]

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Only add features if the device supports the module
        if "setup_info_get" not in self.data:
            return

        self._add_feature(
            Feature(
                self._device,
                container=self,
                id="homekit_setup_code",
                name="HomeKit setup code",
                attribute_getter="setup_code",
                type=Feature.Type.Sensor,
                category=Feature.Category.Debug,
            )
        )
