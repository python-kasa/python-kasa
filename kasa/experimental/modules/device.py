"""Implementation of device module."""

from __future__ import annotations

from ...feature import Feature
from ..smartcameramodule import SmartCameraModule


class DeviceModule(SmartCameraModule):
    """Implementation of device module."""

    NAME = "devicemodule"
    QUERY_GETTER_NAME = "getDeviceInfo"
    QUERY_MODULE_NAME = "device_info"
    QUERY_SECTION_NAMES = ["basic_info", "info"]

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="device_id",
                name="Device ID",
                attribute_getter="device_id",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    async def _post_update_hook(self) -> None:
        """Overriden to prevent module disabling.

        Overrides the default behaviour to disable a module if the query returns
        an error because this module is critical.
        """

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return self.data["basic_info"]["dev_id"]
