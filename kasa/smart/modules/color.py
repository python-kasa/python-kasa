"""Implementation of color module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ...interfaces.light import HSV
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class Color(SmartModule):
    """Implementation of color module."""

    REQUIRED_COMPONENT = "color"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "hsv",
                "HSV",
                container=self,
                attribute_getter="hsv",
                attribute_setter="set_hsv",
                # TODO proper type for setting hsv
                type=Feature.Type.Unknown,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        # HSV is contained in the main device info response.
        return {}

    @property
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, 1-100)
        """
        h, s, v = (
            self.data.get("hue", 0),
            self.data.get("saturation", 0),
            self.data.get("brightness", 0),
        )

        return HSV(hue=h, saturation=s, value=v)

    def _raise_for_invalid_brightness(self, value: int):
        """Raise error on invalid brightness value."""
        if not isinstance(value, int) or not (1 <= value <= 100):
            raise ValueError(f"Invalid brightness value: {value} (valid range: 1-100%)")

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> dict:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """
        if not isinstance(hue, int) or not (0 <= hue <= 360):
            raise ValueError(f"Invalid hue value: {hue} (valid range: 0-360)")

        if not isinstance(saturation, int) or not (0 <= saturation <= 100):
            raise ValueError(
                f"Invalid saturation value: {saturation} (valid range: 0-100%)"
            )

        if value is not None:
            self._raise_for_invalid_brightness(value)

        request_payload = {
            "color_temp": 0,  # If set, color_temp takes precedence over hue&sat
            "hue": hue,
            "saturation": saturation,
        }
        # The device errors on invalid brightness values.
        if value is not None:
            request_payload["brightness"] = value

        return await self.call("set_device_info", {**request_payload})
