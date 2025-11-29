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
    _presets: dict[str, str] = {}

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

    async def _post_update_hook(self) -> None:
        """Update presets after update."""
        presets_response = await self._device._query_helper(
            "getPresetConfig", {"preset": {"name": ["preset"]}}
        )
        presets_data = presets_response.get("getPresetConfig", presets_response)
        if "preset" in presets_data and "preset" in presets_data["preset"]:
            preset_info = presets_data["preset"]["preset"]
            self._presets = {
                name: preset_id
                for preset_id, name in zip(
                    preset_info.get("id", []), preset_info.get("name", []), strict=False
                )
            }

        if self._presets and "preset" not in self._module_features:

            async def set_preset(preset_name: str) -> None:
                preset_id = self._presets.get(preset_name)
                if preset_id:
                    await self.goto_preset(preset_id)

            feature = Feature(
                self._device,
                "preset",
                "Preset position",
                container=self,
                attribute_getter=lambda x: next(iter(self._presets.keys()), None),
                attribute_setter=set_preset,
                choices_getter=lambda: list(self._presets.keys()),
                type=Feature.Type.Choice,
            )
            self._add_feature(feature)

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"getPresetConfig": {"preset": {"name": ["preset"]}}}

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
