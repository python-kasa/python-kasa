"""Implementation of brightness module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...interfaces import Brightness as BrightnessInterface
from ..iotmodule import IotModule

if TYPE_CHECKING:
    from ..iotbulb import IotBulb
    from ..iotdimmer import IotDimmer


BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100


class Brightness(IotModule, BrightnessInterface):
    """Implementation of brightness module."""

    _device: IotBulb | IotDimmer

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    @property  # type: ignore
    def brightness(self) -> int:
        """Return the current brightness in percentage."""
        return self._device.brightness

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> None:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        await self._device.set_brightness(brightness, transition=transition)
