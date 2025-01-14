from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import get_parent_and_child_modules, parametrize

speaker = parametrize(
    "has speaker", component_filter="speaker", protocol_filter={"SMART"}
)


@speaker
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("volume", "volume", int),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    speaker = next(get_parent_and_child_modules(dev, Module.Speaker))
    assert speaker is not None

    prop = getattr(speaker, prop_name)
    assert isinstance(prop, type)

    feat = speaker._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@speaker
async def test_set_volume(dev: SmartDevice, mocker: MockerFixture):
    """Test speaker settings."""
    speaker = next(get_parent_and_child_modules(dev, Module.Speaker))
    assert speaker is not None

    call = mocker.spy(speaker, "call")

    volume = speaker._device.features["volume"]
    assert speaker.volume == volume.value

    new_volume = 15
    await speaker.set_volume(new_volume)

    call.assert_called_with("setVolume", {"volume": new_volume})

    await dev.update()

    assert speaker.volume == new_volume


@speaker
async def test_locate(dev: SmartDevice, mocker: MockerFixture):
    """Test the locate method."""
    speaker = next(get_parent_and_child_modules(dev, Module.Speaker))
    call = mocker.spy(speaker, "call")

    await speaker.locate()

    call.assert_called_with("playSelectAudio", {"audio_type": "seek_me"})
