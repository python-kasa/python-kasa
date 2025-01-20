from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.consumables import CONSUMABLE_METAS

from ...device_fixtures import get_parent_and_child_modules, parametrize

consumables = parametrize(
    "has consumables", component_filter="consumables", protocol_filter={"SMART"}
)


@consumables
@pytest.mark.parametrize(
    "consumable_name", [consumable.id for consumable in CONSUMABLE_METAS]
)
@pytest.mark.parametrize("postfix", ["used", "remaining"])
async def test_features(dev: SmartDevice, consumable_name: str, postfix: str):
    """Test that features are registered and work as expected."""
    consumables = next(get_parent_and_child_modules(dev, Module.Consumables))
    assert consumables is not None

    feature_name = f"{consumable_name}_{postfix}"

    feat = consumables._device.features[feature_name]
    assert isinstance(feat.value, timedelta)


@consumables
@pytest.mark.parametrize(
    ("consumable_name", "data_key"),
    [(consumable.id, consumable.data_key) for consumable in CONSUMABLE_METAS],
)
async def test_erase(
    dev: SmartDevice, mocker: MockerFixture, consumable_name: str, data_key: str
):
    """Test autocollection switch."""
    consumables = next(get_parent_and_child_modules(dev, Module.Consumables))
    call = mocker.spy(consumables, "call")

    feature_name = f"{consumable_name}_reset"
    feat = dev._features[feature_name]
    await feat.set_value(True)

    call.assert_called_with(
        "resetConsumablesTime", {"reset_list": [data_key.removesuffix("_time")]}
    )
