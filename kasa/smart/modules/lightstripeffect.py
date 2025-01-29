"""Module for light effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects import EFFECT_MAPPING, EFFECT_NAMES, SmartLightEffect
from ..smartmodule import Module, SmartModule, allow_update_after

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class LightStripEffect(SmartModule, SmartLightEffect):
    """Implementation of dynamic light effects."""

    REQUIRED_COMPONENT = "light_strip_lighting_effect"

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        effect_list = [self.LIGHT_EFFECTS_OFF]
        effect_list.extend(EFFECT_NAMES)
        self._effect_list = effect_list
        self._effect_mapping = EFFECT_MAPPING

    @property
    def name(self) -> str:
        """Name of the module.

        By default smart modules are keyed in the module mapping by class name.
        The name is overriden here as this module implements the same common interface
        as the bulb light_effect and the assumption is a device only supports one
        or the other.

        """
        return "LightEffect"

    @property
    def effect(self) -> str:
        """Return effect name."""
        eff = self.data["lighting_effect"]
        name = eff["name"]
        # When devices are unpaired effect name is softAP which is not in our list
        if eff["enable"] and name in self._effect_list:
            return name
        if eff["enable"] and eff["custom"]:
            return name or self.LIGHT_EFFECTS_UNNAMED_CUSTOM
        return self.LIGHT_EFFECTS_OFF

    @property
    def is_active(self) -> bool:
        """Return if effect is active."""
        eff = self.data["lighting_effect"]
        # softAP has enable=1, but brightness 0 which fails on tests
        return bool(eff["enable"]) and eff["name"] in self._effect_list

    @property
    def brightness(self) -> int:
        """Return effect brightness."""
        eff = self.data["lighting_effect"]
        return eff["brightness"]

    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set effect brightness."""
        if brightness <= 0:
            return await self.set_effect(self.LIGHT_EFFECTS_OFF)

        # Need to pass bAdjusted to keep the existing effect running
        eff = {"brightness": brightness, "bAdjusted": True}
        return await self.set_custom_effect(eff)

    @property
    def effect_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """
        return self._effect_list

    @allow_update_after
    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> dict:
        """Set an effect on the device.

        If brightness or transition is defined,
        its value will be used instead of the effect-specific default.

        See :meth:`effect_list` for available effects,
        or use :meth:`set_custom_effect` for custom effects.

        :param str effect: The effect to set
        :param int brightness: The wanted brightness
        :param int transition: The wanted transition time
        """
        brightness_module = self._device.modules[Module.Brightness]
        if effect == self.LIGHT_EFFECTS_OFF:
            if self.effect in self._effect_mapping:
                # TODO: We could query get_lighting_effect here to
                # get the custom effect although not sure how to find
                # custom effects
                effect_dict = self._effect_mapping[self.effect]
            else:
                effect_dict = self._effect_mapping["Aurora"]
            effect_dict = {**effect_dict}
            effect_dict["enable"] = 0
            return await self.set_custom_effect(effect_dict)

        if effect not in self._effect_mapping:
            raise ValueError(f"The effect {effect} is not a built in effect.")
        else:
            effect_dict = self._effect_mapping[effect]
            effect_dict = {**effect_dict}

        # Use explicitly given brightness
        if brightness is not None:
            effect_dict["brightness"] = brightness
        # Fall back to brightness reported by the brightness module
        elif brightness_module.brightness:
            effect_dict["brightness"] = brightness_module.brightness

        if transition is not None:
            effect_dict["transition"] = transition

        return await self.set_custom_effect(effect_dict)

    @allow_update_after
    async def set_custom_effect(
        self,
        effect_dict: dict,
    ) -> dict:
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

    def query(self) -> dict:
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
        return self.data["lighting_effect"]

    @property  # type: ignore
    def _deprecated_effect_list(self) -> list[str] | None:
        """Return built-in effects list.

        Example:
            ['Aurora', 'Bubbling Cauldron', ...]
        """
        # LightEffectModule returns effect names along with a LIGHT_EFFECTS_OFF value
        # so return the original effect names here for backwards compatibility
        return EFFECT_NAMES
