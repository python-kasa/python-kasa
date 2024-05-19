"""Light preset module."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Optional, Sequence

from pydantic.v1 import BaseModel, Field

from ...exceptions import KasaException
from ...interfaces import LightPreset as LightPresetInterface
from ...interfaces import LightState
from ...module import Module
from ..iotmodule import IotModule

if TYPE_CHECKING:
    pass


class IotLightPreset(BaseModel, LightState):
    """Light configuration preset."""

    index: int = Field(kw_only=True)
    brightness: int = Field(kw_only=True)

    # These are not available for effect mode presets on light strips
    hue: Optional[int] = Field(kw_only=True, default=None)  # noqa: UP007
    saturation: Optional[int] = Field(kw_only=True, default=None)  # noqa: UP007
    color_temp: Optional[int] = Field(kw_only=True, default=None)  # noqa: UP007

    # Variables for effect mode presets
    custom: Optional[int] = Field(kw_only=True, default=None)  # noqa: UP007
    id: Optional[str] = Field(kw_only=True, default=None)  # noqa: UP007
    mode: Optional[int] = Field(kw_only=True, default=None)  # noqa: UP007


class LightPreset(IotModule, LightPresetInterface):
    """Class for setting light presets."""

    _presets: dict[str, IotLightPreset]
    _preset_list: list[str]

    def _post_update_hook(self):
        """Update the internal presets."""
        self._presets = {
            f"Light preset {index+1}": IotLightPreset(**vals)
            for index, vals in enumerate(self.data["preferred_state"])
        }
        self._preset_list = [self.PRESET_NOT_SET]
        self._preset_list.extend(self._presets.keys())

    @property
    def preset_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Off', 'Preset 1', 'Preset 2', ...]
        """
        return self._preset_list

    @property
    def preset_states_list(self) -> Sequence[IotLightPreset]:
        """Return built-in effects list.

        Example:
            ['Off', 'Preset 1', 'Preset 2', ...]
        """
        return list(self._presets.values())

    @property
    def preset(self) -> str:
        """Return current preset name."""
        light = self._device.modules[Module.Light]
        brightness = light.brightness
        color_temp = light.color_temp if light.is_variable_color_temp else None
        h, s = (light.hsv.hue, light.hsv.saturation) if light.is_color else (None, None)
        for preset_name, preset in self._presets.items():
            if (
                preset.brightness == brightness
                and (
                    preset.color_temp == color_temp or not light.is_variable_color_temp
                )
                and (preset.hue == h or not light.is_color)
                and (preset.saturation == s or not light.is_color)
            ):
                return preset_name
        return self.PRESET_NOT_SET

    async def set_preset(
        self,
        preset_name: str,
    ) -> None:
        """Set a light preset for the device."""
        light = self._device.modules[Module.Light]
        if preset_name == self.PRESET_NOT_SET:
            if light.is_color:
                preset = LightState(hue=0, saturation=0, brightness=100)
            else:
                preset = LightState(brightness=100)
        elif (preset := self._presets.get(preset_name)) is None:  # type: ignore[assignment]
            raise ValueError(f"{preset_name} is not a valid preset: {self.preset_list}")

        await light.set_state(preset)

    @property
    def has_save_preset(self) -> bool:
        """Return True if the device supports updating presets."""
        return True

    async def save_preset(
        self,
        preset_name: str,
        preset_state: LightState,
    ) -> None:
        """Update the preset with preset_name with the new preset_info."""
        if len(self._presets) == 0:
            raise KasaException("Device does not supported saving presets")
        if preset_name not in self._presets:
            raise ValueError(f"{preset_name} is not a valid preset: {self.preset_list}")

        index = list(self._presets.keys()).index(preset_name)
        state = asdict(preset_state)
        state = {k: v for k, v in state.items() if v is not None}
        state["index"] = index

        return await self.call("set_preferred_state", state)

    def query(self):
        """Return the base query."""
        return {}

    @property  # type: ignore
    def _deprecated_presets(self) -> list[IotLightPreset]:
        """Return a list of available bulb setting presets."""
        return [
            IotLightPreset(**vals) for vals in self._device.sys_info["preferred_state"]
        ]

    async def _deprecated_save_preset(self, preset: IotLightPreset):
        """Save a setting preset.

        You can either construct a preset object manually, or pass an existing one
        obtained using :func:`presets`.
        """
        if len(self._presets) == 0:
            raise KasaException("Device does not supported saving presets")

        if preset.index >= len(self._presets):
            raise KasaException("Invalid preset index")

        return await self.call("set_preferred_state", preset.dict(exclude_none=True))
