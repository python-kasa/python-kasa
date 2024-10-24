"""Implementation of device module."""

from __future__ import annotations

from ...device_type import DeviceType
from ...feature import Feature
from ..smartcameramodule import SmartCameraModule


class Camera(SmartCameraModule):
    """Implementation of device module."""

    NAME = "Camera"
    QUERY_GETTER_NAME = "getLensMaskConfig"
    QUERY_MODULE_NAME = "lens_mask"
    QUERY_SECTION_NAMES = "lens_mask_info"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        if self.data:
            self._add_feature(
                Feature(
                    self._device,
                    id="state",
                    name="State",
                    attribute_getter="is_on",
                    attribute_setter="set_state",
                    type=Feature.Type.Switch,
                    category=Feature.Category.Primary,
                )
            )

    @property
    def is_on(self) -> bool:
        """Return the device id."""
        return self.data["lens_mask_info"]["enabled"] == "on"

    async def set_state(self, on: bool) -> dict:
        """Set the device state."""
        params = {"enabled": "on" if on else "off"}
        return await self._device._query_setter_helper(
            "setLensMaskConfig", self.QUERY_MODULE_NAME, "lens_mask_info", params
        )

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return self._device.device_type is DeviceType.Camera
