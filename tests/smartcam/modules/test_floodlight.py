"""Tests for smartcam floodlight module."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest

from kasa import Device, KasaException, LightState, Module
from kasa.smartcam.modules import FloodLight
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

floodlight_smartcam = parametrize(
    "has floodlight", component_filter="whiteLamp", protocol_filter={"SMARTCAM"}
)


@floodlight_smartcam
async def test_floodlight_is_on(dev: Device):
    """Test floodlight on/off state reflects fixture data."""
    floodlight = dev.modules.get(Module.FloodLight)
    assert floodlight is not None
    assert dev.modules.get(SmartCamModule.SmartCamFloodLight) is floodlight

    assert isinstance(floodlight.is_on, bool)


@floodlight_smartcam
async def test_floodlight_set_on(dev: Device):
    """Test turning floodlight on and off."""
    floodlight = dev.modules[Module.FloodLight]
    original_state = floodlight.is_on

    try:
        await floodlight.set_on(not original_state)
        await dev.update()
        assert floodlight.is_on is not original_state

        await floodlight.set_on(original_state)
        await dev.update()
        assert floodlight.is_on is original_state
    finally:
        await floodlight.set_on(original_state)
        await dev.update()


@floodlight_smartcam
async def test_floodlight_set_on_idempotent(dev: Device, mocker):
    """Test that set_on does not toggle when already in requested state."""
    floodlight = dev.modules[Module.FloodLight]
    call = mocker.spy(floodlight, "call")

    await floodlight.set_on(floodlight.is_on)
    call.assert_not_called()


@floodlight_smartcam
async def test_floodlight_brightness(dev: Device):
    """Test floodlight brightness getter and setter."""
    floodlight = dev.modules[Module.FloodLight]

    if not floodlight.has_feature("brightness"):
        pytest.skip("Device floodlight does not support brightness control")

    original_brightness = floodlight.brightness
    assert isinstance(original_brightness, int)
    assert 1 <= original_brightness <= 100

    try:
        new_brightness = 50 if original_brightness != 50 else 75
        await floodlight.set_brightness(new_brightness)
        await dev.update()
        assert floodlight.brightness == new_brightness
    finally:
        await floodlight.set_brightness(original_brightness)
        await dev.update()


@floodlight_smartcam
async def test_floodlight_not_dimmable(dev: Device):
    """Test that brightness is not available when the device does not support it."""
    floodlight = dev.modules[Module.FloodLight]
    data = {**floodlight.data}
    data["getWhitelampConfig"] = {"image": {"switch": {}}}

    with patch.object(FloodLight, "data", new_callable=PropertyMock) as mock_data:
        mock_data.return_value = data
        floodlight._module_features.clear()
        floodlight._initialize_features()

        assert "floodlight" in floodlight._module_features
        assert "floodlight_brightness" not in floodlight._module_features
        assert floodlight.state.brightness is None
        with pytest.raises(KasaException, match="not dimmable"):
            _ = floodlight.brightness
        with pytest.raises(KasaException, match="not dimmable"):
            await floodlight.set_brightness(50)


@floodlight_smartcam
async def test_floodlight_features(dev: Device):
    """Test floodlight features are registered on the device."""
    feature = dev.features.get("floodlight")
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


@floodlight_smartcam
async def test_floodlight_state(dev: Device):
    """Test the light interface state."""
    floodlight = dev.modules[Module.FloodLight]
    original_state = floodlight.is_on

    try:
        await floodlight.set_state(LightState(light_on=True))
        await dev.update()
        assert floodlight.state.light_on is True

        await floodlight.set_state(LightState(brightness=0))
        await dev.update()
        assert floodlight.state.light_on is False

        await floodlight.set_state(LightState(brightness=60))
        await dev.update()
        assert floodlight.state.light_on is True
        if floodlight.has_feature("brightness"):
            assert floodlight.state.brightness == 60

        await floodlight.set_state(LightState(light_on=False))
        await dev.update()
        assert floodlight.state.light_on is False

        assert await floodlight.set_state(LightState()) == {}
    finally:
        await floodlight.set_on(original_state)
        await dev.update()


@floodlight_smartcam
async def test_floodlight_unsupported(dev: Device):
    """Test that color and color temperature are not supported."""
    floodlight = dev.modules[Module.FloodLight]

    with pytest.raises(KasaException, match="does not support color"):
        _ = floodlight.hsv
    with pytest.raises(KasaException, match="does not support colortemp"):
        _ = floodlight.color_temp
    with pytest.raises(KasaException, match="does not support color"):
        await floodlight.set_hsv(0, 0, 0)
    with pytest.raises(KasaException, match="does not support colortemp"):
        await floodlight.set_color_temp(2700)
