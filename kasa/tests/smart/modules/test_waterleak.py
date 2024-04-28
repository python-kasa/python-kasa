from enum import Enum

import pytest

from kasa.smart.modules import WaterleakSensor
from kasa.tests.device_fixtures import parametrize

humidity = parametrize(
    "has waterleak", component_filter="sensor_alarm", protocol_filter={"SMART.CHILD"}
)


@humidity
@pytest.mark.parametrize(
    "feature, type",
    [
        ("alert", int),
        ("status", Enum),
    ],
)
async def test_waterleak_features(dev, feature, type):
    """Test that features are registered and work as expected."""
    humidity: WaterleakSensor = dev.modules["WaterleakSensor"]

    prop = getattr(humidity, feature)
    assert isinstance(prop, type)

    feat = humidity._module_features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
