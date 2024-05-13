from enum import Enum

import pytest

from kasa.smart.modules import WaterleakSensor
from kasa.tests.device_fixtures import parametrize

waterleak = parametrize(
    "has waterleak", component_filter="sensor_alarm", protocol_filter={"SMART.CHILD"}
)


@waterleak
@pytest.mark.parametrize(
    "feature, prop_name, type",
    [
        ("water_alert", "alert", int),
        ("water_leak", "status", Enum),
    ],
)
async def test_waterleak_properties(dev, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]

    prop = getattr(waterleak, prop_name)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@waterleak
async def test_waterleak_features(dev):
    """Test waterleak features."""
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]

    assert "water_leak" in dev.features
    assert dev.features["water_leak"].value == waterleak.status

    assert "water_alert" in dev.features
    assert dev.features["water_alert"].value == waterleak.alert
