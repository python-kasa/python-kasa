"""Implementation of pan/tilt module."""

from __future__ import annotations

from ...feature import Feature
from ..smartcammodule import SmartCamModule

DEFAULT_PAN_STEP = 30
DEFAULT_TILT_STEP = 10


class PanTilt(SmartCamModule):
    """Implementation of pan/tilt module for PTZ cameras."""

    REQUIRED_COMPONENT = "ptz"
    QUERY_GETTER_NAME = "getPresetConfig"
    QUERY_MODULE_NAME = "preset"
    QUERY_SECTION_NAMES = ["preset"]

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

        if self._presets:
            self._add_feature(
                Feature(
                    self._device,
                    "ptz_preset",
                    "PTZ Preset",
                    container=self,
                    attribute_getter="preset",
                    attribute_setter="set_preset",
                    choices_getter=lambda: list(self._presets.keys()),
                    type=Feature.Type.Choice,
                )
            )

    @property
    def _presets(self) -> dict[str, str]:
        """Return presets from device data."""
        if "preset" not in self.data:
            return {}
        preset_info = self.data["preset"]
        return {
            name: preset_id
            for preset_id, name in zip(
                preset_info.get("id", []), preset_info.get("name", []), strict=False
            )
        }

    @property
    def preset(self) -> str | None:
        """Return first preset name as current value."""
        return next(iter(self._presets.keys()), None)

    async def set_preset(self, preset: str) -> dict:
        """Set preset by name or ID."""
        preset_id = self._presets.get(preset)
        if preset_id:
            return await self.goto_preset(preset_id)
        if preset in self._presets.values():
            return await self.goto_preset(preset)
        return {}

    @property
    def presets(self) -> dict[str, str]:
        """Return available presets as dict of name -> id."""
        return self._presets

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

    async def get_presets(self) -> dict:
        """Get presets."""
        return await self._device._raw_query(
            {"getPresetConfig": {"preset": {"name": ["preset"]}}}
        )

    async def goto_preset(self, preset_id: str) -> dict:
        """Go to preset."""
        return await self._device._raw_query(
            {"motorMoveToPreset": {"preset": {"goto_preset": {"id": preset_id}}}}
        )

    async def save_preset(self, name: str) -> dict:
        """Save preset."""
        return await self._device._raw_query(
            {
                "addMotorPostion": {  # Note: API has typo in method name
                    "preset": {"set_preset": {"name": name, "save_ptz": "1"}}
                }
            }
        )
