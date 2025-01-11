from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import get_parent_and_child_modules, parametrize

dustbin = parametrize(
    "has dustbin", component_filter="dustbin", protocol_filter={"SMART"}
)


@dustbin
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("dustbin_autocollection_enabled", "auto_collection", bool),
        ("dustbin_mode", "mode", str),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    dustbin = next(get_parent_and_child_modules(dev, Module.Dustbin))
    assert dustbin is not None

    prop = getattr(dustbin, prop_name)
    assert isinstance(prop, type)

    feat = dustbin._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@dustbin
async def test_dustbin_mode(dev: SmartDevice, mocker: MockerFixture):
    """Test dust mode."""
    dustbin = next(get_parent_and_child_modules(dev, Module.Dustbin))
    call = mocker.spy(dustbin, "call")

    mode_feature = dustbin._device.features["mode"]
    assert dustbin.mode == mode_feature.mode

    new_mode = "Max"
    await dustbin.set_mode(new_mode)

    params = dustbin._settings.copy()
    # TODO: fix hardcoding
    params["dust_colection_mode"] = 4

    call.assert_called_with("setDustCollectionInfo", {"dust_collection_mode": params})

    await dev.update()

    assert dustbin.mode == new_mode


@dustbin
async def test_autocollection(dev: SmartDevice, mocker: MockerFixture):
    """Test autocollection switch."""
    dustbin = next(get_parent_and_child_modules(dev, Module.Dustbin))
    call = mocker.spy(dustbin, "call")

    auto_collection = dustbin._device.features["auto_collection"]
    assert dustbin.auto_collection == auto_collection.value

    params = dustbin._settings.copy()
    params["auto_dust_collection"] = True

    call.assert_called_with("setDustCollectionInfo", {"dust_collection_mode": params})

    await dev.update()

    assert dustbin.auto_collection is True


@dustbin
async def test_empty_dustbin(dev: SmartDevice, mocker: MockerFixture):
    """Test the empty dustbin feature."""
    speaker = next(get_parent_and_child_modules(dev, Module.Dustbin))
    call = mocker.spy(speaker, "call")

    call.assert_called_with("setSwitchDustCollection", {"switch_dust_collection": True})
