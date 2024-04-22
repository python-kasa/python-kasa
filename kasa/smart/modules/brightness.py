"""Implementation of brightness module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


BRIGHTNESS_MIN = 1
BRIGHTNESS_MAX = 100


class Brightness(SmartModule):
    """Implementation of brightness module."""

    REQUIRED_COMPONENT = "brightness"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Brightness",
                container=self,
                attribute_getter="brightness",
                attribute_setter="set_brightness",
                minimum_value=BRIGHTNESS_MIN,
                maximum_value=BRIGHTNESS_MAX,
                type=FeatureType.Number,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    @property
    def brightness(self):
        """Return current brightness."""
        return self.data["brightness"]

    async def set_brightness(self, brightness: int):
        """Set the brightness."""
        if not isinstance(brightness, int) or not (
            BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
        ):
            raise ValueError(
                f"Invalid brightness value: {brightness} "
                f"(valid range: {BRIGHTNESS_MIN}-{BRIGHTNESS_MAX}%)"
            )

        return await self.call("set_device_info", {"brightness": brightness})
