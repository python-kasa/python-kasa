"""Interact with TPLink Light Presets.

>>> from kasa import Discover, Module, LightState
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.3",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>> await dev.update()
>>> print(dev.alias)
Living Room Bulb

Light presets are accessed via the LightPreset module. To list available presets

>>> light_preset = dev.modules[Module.LightPreset]
>>> light_preset.preset_list
['Not set', 'Light preset 1', 'Light preset 2', 'Light preset 3',\
 'Light preset 4', 'Light preset 5', 'Light preset 6', 'Light preset 7']

To view the currently selected preset:

>>> light_preset.preset
Not set

To view the actual light state for the presets:

>>> len(light_preset.preset_states_list)
7

>>> light_preset.preset_states_list[0]
LightState(light_on=None, brightness=50, hue=0,\
 saturation=100, color_temp=2700, transition=None)

To set a preset as active:

>>> dev.modules[Module.Light].state  # This is only needed to show the example working
LightState(light_on=True, brightness=100, hue=0,\
 saturation=100, color_temp=2700, transition=None)
>>> await light_preset.set_preset("Light preset 1")
>>> await dev.update()
>>> light_preset.preset
Light preset 1
>>> dev.modules[Module.Light].state  # This is only needed to show the example working
LightState(light_on=True, brightness=50, hue=0,\
 saturation=100, color_temp=2700, transition=None)

You can save a new preset state if the device supports it:

>>> if light_preset.has_save_preset:
>>>     new_preset_state = LightState(light_on=True, brightness=75, hue=0,\
 saturation=100, color_temp=2700, transition=None)
>>>     await light_preset.save_preset("Light preset 1", new_preset_state)
>>> await dev.update()
>>> light_preset.preset  # Saving updates the preset state for the preset, it does not \
set the preset
Not set
>>> light_preset.preset_states_list[0]
LightState(light_on=None, brightness=75, hue=0,\
 saturation=100, color_temp=2700, transition=None)

If you manually set the light state to a preset state it will show that preset as \
    active:

>>> await dev.modules[Module.Light].set_brightness(75)
>>> await dev.update()
>>> light_preset.preset
Light preset 1
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence

from ..feature import Feature
from ..module import Module
from .light import LightState


class LightPreset(Module):
    """Base interface for light preset module."""

    PRESET_NOT_SET = "Not set"

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="light_preset",
                name="Light preset",
                container=self,
                attribute_getter="preset",
                attribute_setter="set_preset",
                category=Feature.Category.Config,
                type=Feature.Type.Choice,
                choices_getter="preset_list",
            )
        )

    @property
    @abstractmethod
    def preset_list(self) -> list[str]:
        """Return list of preset names.

        Example:
            ['Off', 'Preset 1', 'Preset 2', ...]
        """

    @property
    @abstractmethod
    def preset_states_list(self) -> Sequence[LightState]:
        """Return list of preset states.

        Example:
            ['Off', 'Preset 1', 'Preset 2', ...]
        """

    @property
    @abstractmethod
    def preset(self) -> str:
        """Return current preset name."""

    @abstractmethod
    async def set_preset(
        self,
        preset_name: str,
    ) -> None:
        """Set a light preset for the device."""

    @abstractmethod
    async def save_preset(
        self,
        preset_name: str,
        preset_info: LightState,
    ) -> None:
        """Update the preset with *preset_name* with the new *preset_info*."""

    @property
    @abstractmethod
    def has_save_preset(self) -> bool:
        """Return True if the device supports updating presets."""
