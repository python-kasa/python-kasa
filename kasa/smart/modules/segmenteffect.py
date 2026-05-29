"""Module for RGBIC light-strip per-segment effects (Tapo app "segment" effects).

DRAFT for python-kasa (target: kasa/smart/modules/segmenteffect.py).
Implements the `segment_effect` SMART component used by RGBIC strips such as the
Tapo L930 for the per-segment custom effects you create in the Tapo app
(breathe / circulating / chasing / flicker / bloom / stacking).

These are a SEPARATE subsystem from `lighting_effect` (handled by LightStripEffect):
they are activated with the `apply_segment_effect_rule` method, not
`set_lighting_effect`. Verified against a live L930 and the reverse-engineered
`SegmentEffect` schema in the mihai-dinculescu/tapo library.

COEXISTENCE NOTE
----------------
`LightStripEffect` renames itself to "LightEffect" assuming a device supports only
one effect system. RGBIC strips expose BOTH `light_strip_lighting_effect` and
`segment_effect`, so this module keeps its own name ("SegmentEffect") to avoid the
clash. Surfacing it in Home Assistant requires either exposing it as a second
effect source (e.g. a dedicated select) or unifying the two effect lists upstream.

WIRING (to register the module):
    * add `from .segmenteffect import SegmentEffect` and `"SegmentEffect"` to
      kasa/smart/modules/__init__.py
    * add `SegmentEffect: Final[ModuleName[...]] = ModuleName("SegmentEffect")`
      to the Module container in kasa/module.py
"""

from __future__ import annotations

from typing import Any

from ..smartmodule import SmartModule, allow_update_after


class SegmentEffect(SmartModule):
    """Per-segment dynamic light effects for RGBIC strips."""

    REQUIRED_COMPONENT = "segment_effect"

    OFF = "Off"

    def query(self) -> dict:
        """Fetch the currently active segment effect rule.

        The saved-effect list comes from `get_preset_rules`, which is already
        fetched by the LightPreset module (REQUIRED_COMPONENT="preset"); we reuse
        it instead of issuing a duplicate query.
        """
        return {"get_segment_effect_rule": None}

    # --- helpers -----------------------------------------------------------

    @property
    def _active_rule(self) -> dict[str, Any]:
        # Single-key queries are unwrapped by SmartModule.data, so this is the
        # get_segment_effect_rule payload directly.
        rule = self.data
        return rule if isinstance(rule, dict) else {}

    @property
    def _preset_states(self) -> list[dict[str, Any]]:
        # Reuse get_preset_rules fetched by the LightPreset module.
        preset_rules = self._device._last_update.get("get_preset_rules") or {}
        return preset_rules.get("states") or []

    def _custom_effects(self) -> dict[str, dict[str, Any]]:
        """Map name -> stored segment_effect rule, for saved custom effects."""
        effects: dict[str, dict[str, Any]] = {}
        for state in self._preset_states:
            if not isinstance(state, dict):
                continue
            rule = state.get("segment_effect")
            if isinstance(rule, dict) and rule.get("custom") and rule.get("name"):
                effects[rule["name"]] = rule
        return effects

    @staticmethod
    def _build_payload(
        rule: dict[str, Any], *, enable: bool, brightness: int | None = None
    ) -> dict[str, Any]:
        """Build the apply_segment_effect_rule payload from a stored rule.

        `deviceType: "strip"` is required for custom effects, and `speed` must be
        included or the firmware resets it to 0 (no animation).
        """
        states = rule.get("states") or []
        payload: dict[str, Any] = {
            "brightness": brightness
            if brightness is not None
            else rule.get("brightness", 100),
            "custom": 1,
            "deviceType": "strip",
            "display_colors": rule.get("display_colors") or states,
            "enable": 1 if enable else 0,
            "id": rule.get("id", ""),
            "name": rule.get("name", "Custom"),
            "segments": rule.get("segments") or [],
            "states": states,
            "type": rule.get("type", "breathe"),
        }
        if rule.get("speed") is not None:
            payload["speed"] = rule["speed"]
        if rule.get("carousel") is not None:
            payload["carousel"] = rule["carousel"]
        return payload

    # --- LightEffect-like interface ---------------------------------------

    @property
    def has_custom_effects(self) -> bool:
        """Return True if the device supports setting custom effects."""
        return True

    @property
    def effect_list(self) -> list[str]:
        """Return the saved custom segment effects (plus an Off entry)."""
        return [self.OFF, *self._custom_effects()]

    @property
    def effect(self) -> str:
        """Return the name of the active segment effect, or Off."""
        rule = self._active_rule
        if rule.get("enable") and rule.get("name"):
            return rule["name"]
        return self.OFF

    @property
    def is_active(self) -> bool:
        """Return whether a segment effect is currently running."""
        return bool(self._active_rule.get("enable"))

    @property
    def brightness(self) -> int:
        """Return the active effect brightness."""
        return self._active_rule.get("brightness", 0)

    @allow_update_after
    async def set_effect(
        self,
        effect: str,
        *,
        brightness: int | None = None,
        transition: int | None = None,
    ) -> dict:
        """Activate a saved segment effect by name, or Off to disable it."""
        if effect == self.OFF:
            return await self._disable()
        effects = self._custom_effects()
        if effect not in effects:
            raise ValueError(f"Unknown segment effect: {effect}")
        payload = self._build_payload(
            effects[effect], enable=True, brightness=brightness
        )
        return await self.call("apply_segment_effect_rule", payload)

    @allow_update_after
    async def set_custom_effect(self, effect_dict: dict) -> dict:
        """Apply a fully-specified segment effect rule."""
        payload = self._build_payload(
            effect_dict, enable=bool(effect_dict.get("enable", 1))
        )
        return await self.call("apply_segment_effect_rule", payload)

    @allow_update_after
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Adjust brightness of the running segment effect."""
        rule = self._active_rule
        if not rule.get("enable"):
            return {}
        payload = self._build_payload(rule, enable=True, brightness=brightness)
        return await self.call("apply_segment_effect_rule", payload)

    async def _disable(self) -> dict:
        rule = dict(self._active_rule)
        if not rule.get("enable"):
            return {}
        rule["enable"] = 0
        rule.setdefault("deviceType", "strip")
        return await self.call("apply_segment_effect_rule", rule)
