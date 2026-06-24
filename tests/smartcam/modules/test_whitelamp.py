"""Tests for smartcam white lamp (floodlight) module."""

from __future__ import annotations

import pytest

from kasa import Device, Module

from ...device_fixtures import parametrize

whitelamp_smartcam = parametrize(
    "has white lamp", component_filter="whiteLamp", protocol_filter={"SMARTCAM"}
)


@whitelamp_smartcam
async def test_whitelamp_is_on(dev: Device):
    """Test white lamp on/off state reflects fixture data."""
    whitelamp = dev.modules.get(Module.WhiteLamp)
    assert whitelamp is not None

    assert isinstance(whitelamp.is_on, bool)


@whitelamp_smartcam
async def test_whitelamp_set_state(dev: Device):
    """Test turning white lamp on and off."""
    whitelamp = dev.modules.get(Module.WhiteLamp)
    assert whitelamp is not None

    original_state = whitelamp.is_on

    try:
        await whitelamp.set_state(not original_state)
        await dev.update()
        assert whitelamp.is_on is not original_state

        await whitelamp.set_state(original_state)
        await dev.update()
        assert whitelamp.is_on is original_state
    finally:
        await whitelamp.set_state(original_state)
        await dev.update()


@whitelamp_smartcam
async def test_whitelamp_set_state_idempotent(dev: Device):
    """Test that set_state does not toggle when already in requested state."""
    whitelamp = dev.modules.get(Module.WhiteLamp)
    assert whitelamp is not None

    original_state = whitelamp.is_on

    try:
        await whitelamp.set_state(original_state)
        await dev.update()
        assert whitelamp.is_on is original_state
    finally:
        await whitelamp.set_state(original_state)
        await dev.update()


@whitelamp_smartcam
async def test_whitelamp_brightness(dev: Device):
    """Test white lamp brightness getter and setter."""
    whitelamp = dev.modules.get(Module.WhiteLamp)
    assert whitelamp is not None

    if not whitelamp.has_feature("brightness"):
        pytest.skip("Device white lamp does not support brightness control")

    original_brightness = whitelamp.brightness
    assert isinstance(original_brightness, int)
    assert 1 <= original_brightness <= 100

    try:
        new_brightness = 50 if original_brightness != 50 else 75
        await whitelamp.set_brightness(new_brightness)
        await dev.update()
        assert whitelamp.brightness == new_brightness
    finally:
        await whitelamp.set_brightness(original_brightness)
        await dev.update()


@whitelamp_smartcam
async def test_whitelamp_features(dev: Device):
    """Test white lamp features are registered on the device."""
    whitelamp = dev.modules.get(Module.WhiteLamp)
    assert whitelamp is not None

    feature = dev.features.get("white_lamp_state")
    assert feature is not None
    assert isinstance(feature.value, bool)

    original_state = feature.value
    try:
        await feature.set_value(not original_state)
        await dev.update()
        assert feature.value is not original_state
    finally:
        await feature.set_value(original_state)
        await dev.update()
