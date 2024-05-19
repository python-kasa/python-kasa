"""Module for light effects."""

from __future__ import annotations

import base64
import copy
from typing import Any

from ...interfaces.lighteffect import LightEffect as LightEffectInterface
from ..smartmodule import SmartModule


class LightEffect(SmartModule, LightEffectInterface):
    """Implementation of dynamic light effects."""

    REQUIRED_COMPONENT = "light_effect"
    QUERY_GETTER_NAME = "get_dynamic_light_effect_rules"
    AVAILABLE_BULB_EFFECTS = {
        "L1": "Party",
        "L2": "Relax",
    }

    _effect: str
    _effect_state_list: dict[str, dict[str, Any]]
    _effect_list: list[str]
    _scenes_names_to_id: dict[str, str]

    def _post_update_hook(self) -> None:
        """Update internal effect state."""
        # Copy the effects so scene name updates do not update the underlying dict.
        effects = copy.deepcopy(
            {effect["id"]: effect for effect in self.data["rule_list"]}
        )
        for effect in effects.values():
            if not effect["scene_name"]:
                # If the name has not been edited scene_name will be an empty string
                effect["scene_name"] = self.AVAILABLE_BULB_EFFECTS[effect["id"]]
            else:
                # Otherwise it will be b64 encoded
                effect["scene_name"] = base64.b64decode(effect["scene_name"]).decode()

        self._effect_state_list = effects
        self._effect_list = [self.LIGHT_EFFECTS_OFF]
        self._effect_list.extend([effect["scene_name"] for effect in effects.values()])
        self._scenes_names_to_id = {
            effect["scene_name"]: effect["id"] for effect in effects.values()
        }
        # get_dynamic_light_effect_rules also has an enable property and current_rule_id
        # property that could be used here as an alternative
        if self._device._info["dynamic_light_effect_enable"]:
            self._effect = self._effect_state_list[
                self._device._info["dynamic_light_effect_id"]
            ]["scene_name"]
        else:
            self._effect = self.LIGHT_EFFECTS_OFF

    @property
    def effect_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Party', 'Relax', ...]
        """
        return self._effect_list

    @property
    def effect(self) -> str:
        """Return effect name."""
        return self._effect

    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> None:
        """Set an effect for the device.

        The device doesn't store an active effect while not enabled so store locally.
        """
        if effect != self.LIGHT_EFFECTS_OFF and effect not in self._scenes_names_to_id:
            raise ValueError(
                f"Cannot set light effect to {effect}, possible values "
                f"are: {self.LIGHT_EFFECTS_OFF} "
                f"{' '.join(self._scenes_names_to_id.keys())}"
            )
        enable = effect != self.LIGHT_EFFECTS_OFF
        params: dict[str, bool | str] = {"enable": enable}
        if enable:
            effect_id = self._scenes_names_to_id[effect]
            params["id"] = effect_id
        return await self.call("set_dynamic_light_effect_rule_enable", params)

    async def set_custom_effect(
        self,
        effect_dict: dict,
    ) -> None:
        """Set a custom effect on the device.

        :param str effect_dict: The custom effect dict to set
        """
        raise NotImplementedError(
            "Device does not support setting custom effects. "
            "Use has_custom_effects to check for support."
        )

    @property
    def has_custom_effects(self) -> bool:
        """Return True if the device supports setting custom effects."""
        return False

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"start_index": 0}}
