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


@segment_effect
async def test_segment_effect_properties(dev: Device) -> None:
    """Module exposes custom-effect capability and brightness."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    assert segment.has_custom_effects is True
    assert isinstance(segment.brightness, int)


@segment_effect
async def test_segment_set_custom_effect(dev: Device, mocker: MockerFixture) -> None:
    """A fully-specified rule is sent verbatim; speed/carousel are optional."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)
    call = mocker.spy(segment, "call")

    await segment.set_custom_effect(
        {
            "id": "TapoStrip_test",
            "name": "Custom test",
            "type": "breathe",
            "segments": [50],
            "states": [[10, 89, 100, 0]],
            "brightness": 50,
            "speed": 8,
            "carousel": 1,
            "enable": 1,
        }
    )
    method, payload = call.call_args[0]
    assert method == "apply_segment_effect_rule"
    assert payload["deviceType"] == "strip"
    assert payload["speed"] == 8
    assert payload["carousel"] == 1
    assert payload["enable"] == 1

    # A minimal rule omits speed/carousel rather than sending them as defaults.
    await segment.set_custom_effect(
        {
            "id": "TapoStrip_min",
            "name": "Minimal",
            "type": "bloom",
            "segments": [0],
            "states": [[0, 0, 100, 0]],
        }
    )
    _, minimal = call.call_args[0]
    assert "speed" not in minimal
    assert "carousel" not in minimal


@segment_effect
async def test_segment_set_brightness(dev: Device, mocker: MockerFixture) -> None:
    """set_brightness updates a running effect and is a no-op when idle."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    custom = [e for e in segment.effect_list if e != SegmentEffect.OFF]
    if not custom:
        pytest.skip("fixture has no saved custom segment effects")

    await segment.set_effect(custom[0])
    await dev.update()

    call = mocker.spy(segment, "call")
    await segment.set_brightness(42)
    method, payload = call.call_args[0]
    assert method == "apply_segment_effect_rule"
    assert payload["brightness"] == 42
    assert payload["enable"] == 1

    # Once disabled, set_brightness does nothing.
    await segment.set_effect(SegmentEffect.OFF)
    await dev.update()
    call.reset_mock()
    assert await segment.set_brightness(10) == {}
    call.assert_not_called()


@segment_effect
async def test_segment_off_when_idle(dev: Device, mocker: MockerFixture) -> None:
    """Selecting Off while no effect is running sends nothing."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    await segment.set_effect(SegmentEffect.OFF)
    await dev.update()

    call = mocker.spy(segment, "call")
    assert await segment.set_effect(SegmentEffect.OFF) == {}
    call.assert_not_called()


@segment_effect
async def test_segment_custom_effects_skip_non_dict(
    dev: Device, mocker: MockerFixture
) -> None:
    """Non-dict preset entries are ignored when building the effect list."""
    segment = dev.modules.get(Module.SegmentEffect)
    assert isinstance(segment, SegmentEffect)

    injected = {
        "custom": 1,
        "name": "Injected",
        "type": "breathe",
        "segments": [0],
        "states": [[0, 0, 100, 0]],
    }
    mocker.patch.object(
        type(segment),
        "_preset_states",
        new_callable=mocker.PropertyMock,
        return_value=["not-a-dict", {"segment_effect": injected}],
    )
    assert segment._custom_effects() == {"Injected": injected}
