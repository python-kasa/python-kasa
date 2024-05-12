"""Implementation of brightness module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...interfaces.brightness import Brightness as BrightnessInterface
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    pass


class Brightness(SmartModule, BrightnessInterface):
    """Implementation of brightness module."""

    REQUIRED_COMPONENT = "brightness"

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
            self.BRIGHTNESS_MIN <= brightness <= self.BRIGHTNESS_MAX
        ):
            raise ValueError(
                f"Invalid brightness value: {brightness} "
                f"(valid range: {self.BRIGHTNESS_MIN}-{self.BRIGHTNESS_MAX}%)"
            )

        if brightness == 0:
            return await self._device.turn_off()
        return await self.call("set_device_info", {"brightness": brightness})

    async def _check_supported(self):
        """Additional check to see if the module is supported by the device."""
        return "brightness" in self.data
