"""Module for light effects."""

from __future__ import annotations

import base64
import binascii
import contextlib
import copy
from typing import Any

from ..effects import SmartLightEffect
from ..smartmodule import Module, SmartModule, allow_update_after


class LightEffect(SmartModule, SmartLightEffect):
    """Implementation of dynamic light effects."""

    REQUIRED_COMPONENT = "light_effect"
    QUERY_GETTER_NAME = "get_dynamic_light_effect_rules"
    MINIMUM_UPDATE_INTERVAL_SECS = 60 * 60 * 24
    AVAILABLE_BULB_EFFECTS = {
        "L1": "Party",
        "L2": "Relax",
    }

    _effect: str
    _effect_state_list: dict[str, dict[str, Any]]
    _effect_list: list[str]
    _scenes_names_to_id: dict[str, str]

    async def _post_update_hook(self) -> None:
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
                # Otherwise it might be b64 encoded or raw string
                with contextlib.suppress(binascii.Error):
                    effect["scene_name"] = base64.b64decode(
                        effect["scene_name"]
                    ).decode()

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

    @allow_update_after
    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> dict:
        """Set an effect for the device.

        Calling this will modify the brightness of the effect on the device.

        The device doesn't store an active effect while not enabled so store locally.
        """
        if effect != self.LIGHT_EFFECTS_OFF and effect not in self._scenes_names_to_id:
            raise ValueError(
                f"The effect {effect} is not a built in effect. Possible values "
                f"are: {self.LIGHT_EFFECTS_OFF} "
                f"{' '.join(self._scenes_names_to_id.keys())}"
            )
        enable = effect != self.LIGHT_EFFECTS_OFF
        params: dict[str, bool | str] = {"enable": enable}
        if enable:
            effect_id = self._scenes_names_to_id[effect]
            params["id"] = effect_id

            # We set the wanted brightness before activating the effect
            brightness_module = self._device.modules[Module.Brightness]
            brightness = (
                brightness if brightness is not None else brightness_module.brightness
            )
            await self.set_brightness(brightness, effect_id=effect_id)

        return await self.call("set_dynamic_light_effect_rule_enable", params)

    @property
    def is_active(self) -> bool:
        """Return True if effect is active."""
        return bool(self._device._info["dynamic_light_effect_enable"])

    def _get_effect_data(self, effect_id: str | None = None) -> dict[str, Any]:
        """Return effect data for the *effect_id*.

        If *effect_id* is None, return the data for active effect.
        """
        if effect_id is None:
            effect_id = self.data["current_rule_id"]

        return self._effect_state_list[effect_id]

    @property
    def brightness(self) -> int:
        """Return effect brightness."""
        first_color_status = self._get_effect_data()["color_status_list"][0]
        brightness = first_color_status[0]

        return brightness

    @allow_update_after
    async def set_brightness(
        self,
        brightness: int,
        *,
        transition: int | None = None,
        effect_id: str | None = None,
    ) -> dict:
        """Set effect brightness."""
        new_effect = self._get_effect_data(effect_id=effect_id).copy()

        def _replace_brightness(data: list[int], new_brightness: int) -> list[int]:
            """Replace brightness.

            The first element is the brightness, the rest are unknown.
            [[33, 0, 0, 2700], [33, 321, 99, 0], [33, 196, 99, 0], .. ]
            """
            return [new_brightness, data[1], data[2], data[3]]

        new_color_status_list = [
            _replace_brightness(state, brightness)
            for state in new_effect["color_status_list"]
        ]
        new_effect["color_status_list"] = new_color_status_list

        return await self.call("edit_dynamic_light_effect_rule", new_effect)

    @allow_update_after
    async def set_custom_effect(
        self,
        effect_dict: dict,
    ) -> dict:
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
