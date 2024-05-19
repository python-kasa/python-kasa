"""Module for light effects."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Sequence

from ...interfaces import LightPreset as LightPresetInterface
from ...interfaces import LightState
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class LightPreset(SmartModule, LightPresetInterface):
    """Implementation of light presets."""

    REQUIRED_COMPONENT = "preset"
    QUERY_GETTER_NAME = "get_preset_rules"

    SYS_INFO_STATE_KEY = "preset_state"

    _presets: dict[str, LightState]
    _preset_list: list[str]

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._state_in_sysinfo = self.SYS_INFO_STATE_KEY in device.sys_info
        self._brightness_only: bool = False

    def _post_update_hook(self):
        """Update the internal presets."""
        index = 0
        self._presets = {}

        state_key = "states" if not self._state_in_sysinfo else self.SYS_INFO_STATE_KEY
        if preset_states := self.data.get(state_key):
            for preset_state in preset_states:
                color_temp = preset_state.get("color_temp")
                hue = preset_state.get("hue")
                saturation = preset_state.get("saturation")
                self._presets[f"Light preset {index + 1}"] = LightState(
                    brightness=preset_state["brightness"],
                    color_temp=color_temp,
                    hue=hue,
                    saturation=saturation,
                )
                if color_temp is None and hue is None and saturation is None:
                    self._brightness_only = True
                index = index + 1
        elif preset_brightnesses := self.data.get("brightness"):
            self._brightness_only = True
            for preset_brightness in preset_brightnesses:
                self._presets[f"Brightness preset {index + 1}"] = LightState(
                    brightness=preset_brightness,
                )
                index = index + 1

        self._preset_list = [self.PRESET_NOT_SET]
        self._preset_list.extend(self._presets.keys())

    @property
    def preset_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Off', 'Light preset 1', 'Light preset 2', ...]
        """
        return self._preset_list

    @property
    def preset_states_list(self) -> Sequence[LightState]:
        """Return built-in effects list.

        Example:
            ['Off', 'Preset 1', 'Preset 2', ...]
        """
        return list(self._presets.values())

    @property
    def preset(self) -> str:
        """Return current preset name."""
        light = self._device.modules[SmartModule.Light]
        brightness = light.brightness
        color_temp = light.color_temp if light.is_variable_color_temp else None
        h, s = (light.hsv.hue, light.hsv.saturation) if light.is_color else (None, None)
        for preset_name, preset in self._presets.items():
            if (
                preset.brightness == brightness
                and (
                    preset.color_temp == color_temp or not light.is_variable_color_temp
                )
                and preset.hue == h
                and preset.saturation == s
            ):
                return preset_name
        return self.PRESET_NOT_SET

    async def set_preset(
        self,
        preset_name: str,
    ) -> None:
        """Set a light preset for the device."""
        light = self._device.modules[SmartModule.Light]
        if preset_name == self.PRESET_NOT_SET:
            if light.is_color:
                preset = LightState(hue=0, saturation=0, brightness=100)
            else:
                preset = LightState(brightness=100)
        elif (preset := self._presets.get(preset_name)) is None:  # type: ignore[assignment]
            raise ValueError(f"{preset_name} is not a valid preset: {self.preset_list}")
        await self._device.modules[SmartModule.Light].set_state(preset)

    async def save_preset(
        self,
        preset_name: str,
        preset_state: LightState,
    ) -> None:
        """Update the preset with preset_name with the new preset_info."""
        if preset_name not in self._presets:
            raise ValueError(f"{preset_name} is not a valid preset: {self.preset_list}")
        index = list(self._presets.keys()).index(preset_name)
        if self._brightness_only:
            bright_list = [state.brightness for state in self._presets.values()]
            bright_list[index] = preset_state.brightness
            await self.call("set_preset_rules", {"brightness": bright_list})
        else:
            state_params = asdict(preset_state)
            new_info = {k: v for k, v in state_params.items() if v is not None}
            await self.call("edit_preset_rules", {"index": index, "state": new_info})

    @property
    def has_save_preset(self) -> bool:
        """Return True if the device supports updating presets."""
        return True

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        if self._state_in_sysinfo:  # Child lights can have states in the child info
            return {}
        return {self.QUERY_GETTER_NAME: None}
