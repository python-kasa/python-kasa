"""Module for light effects."""

from __future__ import annotations

from ...interfaces.lighteffect import LightEffect as LightEffectInterface
from ..effects import EFFECT_MAPPING_V1, EFFECT_NAMES_V1
from ..iotmodule import IotModule


class LightEffect(IotModule, LightEffectInterface):
    """Implementation of dynamic light effects."""

    @property
    def effect(self) -> str:
        """Return effect state.

        Example:
            {'brightness': 50,
             'custom': 0,
             'enable': 0,
             'id': '',
             'name': ''}
        """
        eff = self.data["lighting_effect_state"]
        name = eff["name"]
        if eff["enable"]:
            return name

        return self.LIGHT_EFFECTS_OFF

    @property
    def effect_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """
        effect_list = [self.LIGHT_EFFECTS_OFF]
        effect_list.extend(EFFECT_NAMES_V1)
        return effect_list

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
        if effect == self.LIGHT_EFFECTS_OFF:
            effect_dict = dict(self.data["lighting_effect_state"])
            effect_dict["enable"] = 0
        elif effect not in EFFECT_MAPPING_V1:
            raise ValueError(f"The effect {effect} is not a built in effect.")
        else:
            effect_dict = EFFECT_MAPPING_V1[effect]

        if brightness is not None:
            effect_dict["brightness"] = brightness
        if transition is not None:
            effect_dict["transition"] = transition

        await self.set_custom_effect(effect_dict)

    async def set_custom_effect(
        self,
        effect_dict: dict,
    ) -> None:
        """Set a custom effect on the device.

        :param str effect_dict: The custom effect dict to set
        """
        return await self.call(
            "set_lighting_effect",
            effect_dict,
        )

    @property
    def has_custom_effects(self) -> bool:
        """Return True if the device supports setting custom effects."""
        return True

    def query(self):
        """Return the base query."""
        return {}

    @property  # type: ignore
    def _deprecated_effect(self) -> dict:
        """Return effect state.

        Example:
            {'brightness': 50,
             'custom': 0,
             'enable': 0,
             'id': '',
             'name': ''}
        """
        # LightEffectModule returns the current effect name
        # so return the dict here for backwards compatibility
        return self.data["lighting_effect_state"]

    @property  # type: ignore
    def _deprecated_effect_list(self) -> list[str] | None:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """
        # LightEffectModule returns effect names along with a LIGHT_EFFECTS_OFF value
        # so return the original effect names here for backwards compatibility
        return EFFECT_NAMES_V1
