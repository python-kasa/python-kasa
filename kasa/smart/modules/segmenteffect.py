"""Module for RGBIC light-strip per-segment effects (Tapo app "segment" effects).

DRAFT for python-kasa (target: kasa/smart/modules/segmenteffect.py).
Implements the `segment_effect` SMART component used by RGBIC strips such as the
Tapo L930 for the per-segment custom effects you create in the Tapo app
(breathe / circulating / chasing / flicker / bloom / stacking / none).

These are a SEPARATE subsystem from `lighting_effect` (handled by LightStripEffect):
they are activated with the `apply_segment_effect_rule` method, not
`set_lighting_effect`. Verified against a live L930 and the reverse-engineered
`SegmentEffect` schema in the mihai-dinculescu/tapo library, cross-checked with
the Tapo Android app v3.18.506 (`SegmentEffectData` bean).

EFFECT TYPES AND RANGES (SegmentEffectData @SerializedName/@IntRange)
--------------------------------------------------------------------
* type: one of breathe, circulating, chasing, stacking, flicker, bloom, none.
* brightness: 1-100.
* speed: 1-10 for the six animated types; 0 only for the static "none" paint
  (speed 0 freezes an animated type, so it is rejected for those).
* per-segment colours (`states` / `display_colors`) are 4 integers [h, s, v, w];
  the 4th channel is 0 in every rule the app writes. `apply_segment_effect_rule`
  tolerates 3-int [h, s, v], but `start_segment_effect_test` rejects them with
  PARAMS_ERROR(-1008), so colours are normalised to 4 ints here.
* `segments` is DUAL-ENCODED by type: for the six animated types it holds group
  SIZES (states[i] colours group i, e.g. [50] = one group spanning all LEDs);
  for the static "none" paint it holds explicit LED INDICES (states[i] colours
  the LED at segments[i], unlisted LEDs stay off).

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

#: Valid segment_effect types (Tapo app v3.18.506 SegmentEffectData decompile).
SEGMENT_EFFECT_TYPES = frozenset(
    {"breathe", "circulating", "chasing", "stacking", "flicker", "bloom", "none"}
)
BRIGHTNESS_MIN = 1
BRIGHTNESS_MAX = 100
SPEED_MIN = 1
SPEED_MAX = 10


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def _normalize_colors(colors: list[Any]) -> list[list[int]]:
    """Normalise per-segment colours to the device's 4-int [h, s, v, w] form.

    Pads 3-int [h, s, v] to [h, s, v, 0] and drops malformed entries. Required by
    start_segment_effect_test, which rejects 3-int colours with PARAMS_ERROR.
    """
    normalised: list[list[int]] = []
    for color in colors:
        if not isinstance(color, list | tuple) or len(color) < 3:
            continue
        ints = [int(c) for c in color][:4]
        ints += [0] * (4 - len(ints))
        normalised.append(ints)
    return normalised


def _dedupe(colors: list[list[int]]) -> list[list[int]]:
    """Return the unique palette, preserving order.

    `display_colors` must be the deduplicated palette; the firmware rejects a
    list with duplicate/oversized entries (PARAMS_ERROR -1008).
    """
    seen: set[tuple[int, ...]] = set()
    palette: list[list[int]] = []
    for color in colors:
        key = tuple(color)
        if key in seen:
            continue
        seen.add(key)
        palette.append(color)
    return palette


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
        """Build the apply_segment_effect_rule / *_test payload from a rule.

        `deviceType: "strip"` is required for custom effects, and `speed` must be
        included or the firmware resets it to 0 (no animation). Per-segment
        colours are normalised to the device's 4-int [h, s, v, w] form,
        `display_colors` is reduced to the unique palette, and brightness/speed
        are clamped to their documented ranges.

        The `segments` field is dual-encoded by `type`: group SIZES for the six
        animated types, explicit LED INDICES for the static "none" paint (see the
        module docstring).
        """
        effect_type = rule.get("type", "breathe")
        if effect_type not in SEGMENT_EFFECT_TYPES:
            raise ValueError(
                f"Invalid segment effect type {effect_type!r}; "
                f"expected one of {sorted(SEGMENT_EFFECT_TYPES)}"
            )
        bri = brightness if brightness is not None else rule.get("brightness", 100)
        states = _normalize_colors(rule.get("states") or [])
        display = rule.get("display_colors")
        display_colors = _dedupe(_normalize_colors(display) if display else states)
        payload: dict[str, Any] = {
            "brightness": _clamp(bri, BRIGHTNESS_MIN, BRIGHTNESS_MAX),
            "custom": 1,
            "deviceType": "strip",
            "display_colors": display_colors,
            "enable": 1 if enable else 0,
            "id": rule.get("id", ""),
            "name": rule.get("name", "Custom"),
            "segments": rule.get("segments") or [],
            "states": states,
            "type": effect_type,
        }
        speed = rule.get("speed")
        if speed is not None:
            # speed 0 is valid only for the static "none" paint.
            speed_min = 0 if effect_type == "none" else SPEED_MIN
            payload["speed"] = _clamp(speed, speed_min, SPEED_MAX)
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

    async def test(self, effect_dict: dict) -> dict:
        """Preview a segment effect rule live without saving it.

        Uses start_segment_effect_test, which plays the rule but does NOT write
        it into the device preset table. This avoids the churn where saving an
        effect makes the firmware (and the Tapo app) rewrite the preset list and
        evict effects no longer present. Call stop_test() to end the preview.
        """
        payload = self._build_payload(
            effect_dict, enable=bool(effect_dict.get("enable", 1))
        )
        return await self.call("start_segment_effect_test", payload)

    async def stop_test(self) -> dict:
        """Stop a live segment effect preview started with test()."""
        return await self.call("stop_segment_effect_test", {})

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
