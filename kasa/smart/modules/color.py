"""Implementation of color module."""

from __future__ import annotations

from ...feature import Feature
from ...interfaces.light import HSV
from ..smartmodule import SmartModule


class Color(SmartModule):
    """Implementation of color module."""

    REQUIRED_COMPONENT = "color"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
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

        # Simple HSV(h, s, v) is less efficent than below
        # due to the cpython implementation.
        return tuple.__new__(HSV, (h, s, v))

    def _raise_for_invalid_brightness(self, value: int) -> None:
        """Raise error on invalid brightness value."""
        if not isinstance(value, int):
            raise TypeError("Brightness must be an integer")
        if not (0 <= value <= 100):
            raise ValueError(f"Invalid brightness value: {value} (valid range: 0-100%)")

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
        if not isinstance(hue, int):
            raise TypeError("Hue must be an integer")
        if not (0 <= hue <= 360):
            raise ValueError(f"Invalid hue value: {hue} (valid range: 0-360)")

        if not isinstance(saturation, int):
            raise TypeError("Saturation must be an integer")
        if not (0 <= saturation <= 100):
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
