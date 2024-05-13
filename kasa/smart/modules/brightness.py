"""Implementation of brightness module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule

BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100


class Brightness(SmartModule):
    """Implementation of brightness module."""

    REQUIRED_COMPONENT = "brightness"

    def _initialize_features(self):
        """Initialize features."""
        super()._initialize_features()

        device = self._device
        self._add_feature(
            Feature(
                device,
                id="brightness",
                name="Brightness",
                container=self,
                attribute_getter="brightness",
                attribute_setter="set_brightness",
                minimum_value=BRIGHTNESS_MIN,
                maximum_value=BRIGHTNESS_MAX,
                type=Feature.Type.Number,
                category=Feature.Category.Primary,
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

    async def set_brightness(self, brightness: int, *, transition: int | None = None):
        """Set the brightness. A brightness value of 0 will turn off the light.

        Note, transition is not supported and will be ignored.
        """
        if not isinstance(brightness, int) or not (
            BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
        ):
            raise ValueError(
                f"Invalid brightness value: {brightness} "
                f"(valid range: {BRIGHTNESS_MIN}-{BRIGHTNESS_MAX}%)"
            )

        if brightness == 0:
            return await self._device.turn_off()
        return await self.call("set_device_info", {"brightness": brightness})

    async def _check_supported(self):
        """Additional check to see if the module is supported by the device."""
        return "brightness" in self.data
