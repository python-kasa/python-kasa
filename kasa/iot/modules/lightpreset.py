"""Light preset module."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from mashumaro.config import BaseConfig

from ...exceptions import KasaException
from ...interfaces import LightPreset as LightPresetInterface
from ...interfaces import LightState
from ...json import DataClassJSONMixin
from ...module import Module
from ..iotmodule import IotModule

if TYPE_CHECKING:
    pass

# type ignore can be removed after migration mashumaro:
# error: Signature of "__replace__" incompatible with supertype "LightState"


@dataclass(kw_only=True, repr=False)
class IotLightPreset(DataClassJSONMixin, LightState):  # type: ignore[override]
    """Light configuration preset."""

    class Config(BaseConfig):
        """Config class."""

        omit_none = True

    index: int
    brightness: int

    # These are not available for effect mode presets on light strips
    hue: int | None = None
    saturation: int | None = None
    color_temp: int | None = None

    # Variables for effect mode presets
    custom: int | None = None
    id: str | None = None
    mode: int | None = None


class LightPreset(IotModule, LightPresetInterface):
    """Class for setting light presets."""

    _presets: dict[str, IotLightPreset]
    _preset_list: list[str]

    async def _post_update_hook(self) -> None:
        """Update the internal presets."""
        self._presets = {
            f"Light preset {index + 1}": IotLightPreset.from_dict(vals)
            for index, vals in enumerate(self.data["preferred_state"])
            # Devices may list some light effects along with normal presets but these
            # are handled by the LightEffect module so exclude preferred states with id
            if "id" not in vals
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
        is_color = light.has_feature("hsv")
        is_variable_color_temp = light.has_feature("color_temp")

        brightness = light.brightness
        color_temp = light.color_temp if is_variable_color_temp else None

        h, s = (light.hsv.hue, light.hsv.saturation) if is_color else (None, None)
        for preset_name, preset in self._presets.items():
            if (
                preset.brightness == brightness
                and (preset.color_temp == color_temp or not is_variable_color_temp)
                and (preset.hue == h or not is_color)
                and (preset.saturation == s or not is_color)
            ):
                return preset_name
        return self.PRESET_NOT_SET

    async def set_preset(
        self,
        preset_name: str,
    ) -> dict:
        """Set a light preset for the device."""
        light = self._device.modules[Module.Light]
        if preset_name == self.PRESET_NOT_SET:
            if light.has_feature("hsv"):
                preset = LightState(hue=0, saturation=0, brightness=100)
            else:
                preset = LightState(brightness=100)
        elif (preset := self._presets.get(preset_name)) is None:  # type: ignore[assignment]
            raise ValueError(f"{preset_name} is not a valid preset: {self.preset_list}")

        return await light.set_state(preset)

    @property
    def has_save_preset(self) -> bool:
        """Return True if the device supports updating presets."""
        return True

    async def save_preset(
        self,
        preset_name: str,
        preset_state: LightState,
    ) -> dict:
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

    def query(self) -> dict:
        """Return the base query."""
        return {}

    @property  # type: ignore
    def _deprecated_presets(self) -> list[IotLightPreset]:
        """Return a list of available bulb setting presets."""
        return [
            IotLightPreset(**vals)
            for vals in self._device.sys_info["preferred_state"]
            if "id" not in vals
        ]

    async def _deprecated_save_preset(self, preset: IotLightPreset) -> dict:
        """Save a setting preset.

        You can either construct a preset object manually, or pass an existing one
        obtained using :func:`presets`.
        """
        if len(self._presets) == 0:
            raise KasaException("Device does not supported saving presets")

        if preset.index >= len(self._presets):
            raise KasaException("Invalid preset index")

        return await self.call("set_preferred_state", preset.to_dict())
