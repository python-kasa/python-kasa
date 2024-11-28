"""Implementation of time module."""

from __future__ import annotations

from ...feature import Feature
from ..smartcammodule import SmartCamModule

DEFAULT_PAN_STEP = 30
DEFAULT_TILT_STEP = 10


class PanTilt(SmartCamModule):
    """Implementation of device_local_time."""

    REQUIRED_COMPONENT = "ptz"
    _pan_step = DEFAULT_PAN_STEP
    _tilt_step = DEFAULT_TILT_STEP

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""

        async def set_pan_step(value: int) -> None:
            self._pan_step = value

        async def set_tilt_step(value: int) -> None:
            self._tilt_step = value

        self._add_feature(
            Feature(
                self._device,
                "pan_right",
                "Pan right",
                container=self,
                attribute_setter=lambda: self.pan(self._pan_step * -1),
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "pan_left",
                "Pan left",
                container=self,
                attribute_setter=lambda: self.pan(self._pan_step),
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "pan_step",
                "Pan step",
                container=self,
                attribute_getter="_pan_step",
                attribute_setter=set_pan_step,
                type=Feature.Type.Number,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "tilt_up",
                "Tilt up",
                container=self,
                attribute_setter=lambda: self.tilt(self._tilt_step),
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "tilt_down",
                "Tilt down",
                container=self,
                attribute_setter=lambda: self.tilt(self._tilt_step * -1),
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                "tilt_step",
                "Tilt step",
                container=self,
                attribute_getter="_tilt_step",
                attribute_setter=set_tilt_step,
                type=Feature.Type.Number,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    async def pan(self, pan: int) -> dict:
        """Pan horizontally."""
        return await self.move(pan=pan, tilt=0)

    async def tilt(self, tilt: int) -> dict:
        """Tilt vertically."""
        return await self.move(pan=0, tilt=tilt)

    async def move(self, *, pan: int, tilt: int) -> dict:
        """Pan and tilt camera."""
        return await self._device._raw_query(
            {"do": {"motor": {"move": {"x_coord": str(pan), "y_coord": str(tilt)}}}}
        )
