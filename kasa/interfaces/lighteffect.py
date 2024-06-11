"""Interact with a TPLink Light Effect.

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

Light effects are accessed via the LightPreset module. To list available presets

>>> if dev.modules[Module.Light].has_effects:
>>>     light_effect = dev.modules[Module.LightEffect]
>>> light_effect.effect_list
['Off', 'Party', 'Relax']

To view the currently selected effect:

>>> light_effect.effect
Off

To activate a light effect:

>>> await light_effect.set_effect("Party")
>>> await dev.update()
>>> light_effect.effect
Party

If the device supports it you can set custom effects:

>>> if light_effect.has_custom_effects:
>>>     effect_list = { "brightness", 50 }
>>>     await light_effect.set_custom_effect(effect_list)
>>> light_effect.has_custom_effects  # The device in this examples does not support \
custom effects
False
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..feature import Feature
from ..module import Module


class LightEffect(Module, ABC):
    """Interface to represent a light effect module."""

    LIGHT_EFFECTS_OFF = "Off"

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="light_effect",
                name="Light effect",
                container=self,
                attribute_getter="effect",
                attribute_setter="set_effect",
                category=Feature.Category.Primary,
                type=Feature.Type.Choice,
                choices_getter="effect_list",
            )
        )

    @property
    @abstractmethod
    def has_custom_effects(self) -> bool:
        """Return True if the device supports setting custom effects."""

    @property
    @abstractmethod
    def effect(self) -> str:
        """Return effect state or name."""

    @property
    @abstractmethod
    def effect_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """

    @abstractmethod
    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> None:
        """Set an effect on the device.

        If brightness or transition is defined,
        its value will be used instead of the effect-specific default.

        See :meth:`effect_list` for available effects,
        or use :meth:`set_custom_effect` for custom effects.

        :param str effect: The effect to set
        :param int brightness: The wanted brightness
        :param int transition: The wanted transition time
        """

    async def set_custom_effect(
        self,
        effect_dict: dict,
    ) -> None:
        """Set a custom effect on the device.

        :param str effect_dict: The custom effect dict to set
        """
