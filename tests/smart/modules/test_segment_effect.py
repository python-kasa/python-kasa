from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Module
from kasa.smart.modules import SegmentEffect

from ...device_fixtures import parametrize

segment_effect = parametrize(
    "has segment effect",
    component_filter="segment_effect",
    protocol_filter={"SMART"},
)


@segment_effect
async def test_segment_effect_list(dev: Device) -> None:
    """Saved custom segment effects are listed with a leading Off entry."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    assert segment.effect_list
    assert segment.effect_list[0] == SegmentEffect.OFF


@segment_effect
async def test_segment_effect_set(dev: Device, mocker: MockerFixture) -> None:
    """Activating a saved effect sends apply_segment_effect_rule and reads back."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    custom = [e for e in segment.effect_list if e != SegmentEffect.OFF]
    if not custom:
        pytest.skip("fixture has no saved custom segment effects")

    call = mocker.spy(segment, "call")

    for effect in custom:
        await segment.set_effect(effect)

        method, payload = call.call_args[0]
        assert method == "apply_segment_effect_rule"
        assert payload["name"] == effect
        assert payload["enable"] == 1
        assert payload["custom"] == 1
        assert payload["deviceType"] == "strip"
        assert "type" in payload

        await dev.update()
        assert segment.effect == effect
        assert segment.is_active

    # Off disables the running effect.
    await segment.set_effect(SegmentEffect.OFF)
    method, payload = call.call_args[0]
    assert method == "apply_segment_effect_rule"
    assert payload["enable"] == 0

    await dev.update()
    assert segment.effect == SegmentEffect.OFF
    assert not segment.is_active


@segment_effect
async def test_segment_effect_unknown(dev: Device) -> None:
    """Setting an unknown effect raises."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    with pytest.raises(ValueError, match="Unknown segment effect"):
        await segment.set_effect("foobar")
