"""Module for light effects."""

from __future__ import annotations

import base64
import copy
from typing import TYPE_CHECKING, Any

from ...interfaces.lighteffect import LightEffect as LightEffectInterface
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class LightEffect(SmartModule, LightEffectInterface):
    """Implementation of dynamic light effects."""

    REQUIRED_COMPONENT = "light_effect"
    QUERY_GETTER_NAME = "get_dynamic_light_effect_rules"
    AVAILABLE_BULB_EFFECTS = {
        "L1": "Party",
        "L2": "Relax",
    }

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._scenes_names_to_id: dict[str, str] = {}

    def _initialize_effects(self) -> dict[str, dict[str, Any]]:
        """Return built-in effects."""
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
        self._scenes_names_to_id = {
            effect["scene_name"]: effect["id"] for effect in effects.values()
        }
        return effects

    @property
    def effect_list(self) -> list[str]:
        """Return built-in effects list.

        Example:
            ['Party', 'Relax', ...]
        """
        effects = [self.LIGHT_EFFECTS_OFF]
        effects.extend(
            [effect["scene_name"] for effect in self._initialize_effects().values()]
        )
        return effects

    @property
    def effect(self) -> str:
        """Return effect name."""
        # get_dynamic_light_effect_rules also has an enable property and current_rule_id
        # property that could be used here as an alternative
        if self._device._info["dynamic_light_effect_enable"]:
            return self._initialize_effects()[
                self._device._info["dynamic_light_effect_id"]
            ]["scene_name"]
        return self.LIGHT_EFFECTS_OFF

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
