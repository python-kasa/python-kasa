from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.mop import Waterlevel

from ...device_fixtures import get_parent_and_child_modules, parametrize

mop = parametrize("has mop", component_filter="mop", protocol_filter={"SMART"})


@mop
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("mop_attached", "mop_attached", bool),
        ("mop_waterlevel", "waterlevel", str),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    mod = next(get_parent_and_child_modules(dev, Module.Mop))
    assert mod is not None

    prop = getattr(mod, prop_name)
    assert isinstance(prop, type)

    feat = mod._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@mop
async def test_mop_waterlevel(dev: SmartDevice, mocker: MockerFixture):
    """Test dust mode."""
    mop_module = next(get_parent_and_child_modules(dev, Module.Mop))
    call = mocker.spy(mop_module, "call")

    waterlevel = mop_module._device.features["mop_waterlevel"]
    assert mop_module.waterlevel == waterlevel.value

    new_level = Waterlevel.High
    await mop_module.set_waterlevel(new_level.name)

    params = mop_module._settings.copy()
    params["cistern"] = new_level.value

    call.assert_called_with("setCleanAttr", params)

    await dev.update()

    assert mop_module.waterlevel == new_level.name

    with pytest.raises(ValueError, match="Invalid waterlevel"):
        await mop_module.set_waterlevel("invalid")
