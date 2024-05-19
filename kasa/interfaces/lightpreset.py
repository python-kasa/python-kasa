"""Module for LightPreset base class."""

from __future__ import annotations

from abc import abstractmethod
from typing import Sequence

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
