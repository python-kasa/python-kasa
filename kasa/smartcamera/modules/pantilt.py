"""Implementation of time module."""

from __future__ import annotations

from ...feature import Feature
from ..smartcameramodule import SmartCameraModule


class PanTilt(SmartCameraModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "ptz"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                "pan",
                "Pan",
                container=self,
                attribute_setter="do_pan",
                type=Feature.Type.Number,
                range_getter=lambda: (-360, 360),
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "tilt",
                "Tilt",
                container=self,
                attribute_setter="do_tilt",
                type=Feature.Type.Number,
                range_getter=lambda: (-180, 180),
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    async def do_pan(self, pan: int) -> dict:
        """Pan horizontally."""
        return await self._device._raw_query(
            {"do": {"motor": {"move": {"x_coord": str(pan), "y_coord": str(0)}}}}
        )

    async def do_tilt(self, tilt: int) -> dict:
        """Tilt vertically horizontally."""
        return await self._device._raw_query(
            {"do": {"motor": {"move": {"x_coord": str(0), "y_coord": str(tilt)}}}}
        )

    async def do_move(self, pan: int, tilt: int) -> dict:
        """Tilt vertically horizontally."""
        return await self._device._raw_query(
            {"do": {"motor": {"move": {"x_coord": str(pan), "y_coord": str(tilt)}}}}
        )
