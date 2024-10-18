import sys
from enum import Enum

import pytest

from kasa.smart.modules import WaterleakSensor
from kasa.tests.device_fixtures import parametrize

waterleak = parametrize(
    "has waterleak", component_filter="sensor_alarm", protocol_filter={"SMART.CHILD"}
)


@waterleak
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("water_alert", "alert", int),
        # Can be enabled after py3.9 support is dropped
        # ("water_alert_timestamp", "alert_timestamp", datetime | None),
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


# Testing this separately as py3.9 does not support union types.
# This can be removed when we drop python3.9 support.
@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="union type requires python3.10+",
)
@waterleak
async def test_waterleak_alert_timestamp(dev):
    """Test that waterleak alert timestamp works."""
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]
    feature = "water_alert_timestamp"
    prop_name = "alert_timestamp"
    prop = getattr(waterleak, prop_name)
    assert isinstance(prop, type) or prop is None

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type) or feat.value is None


@waterleak
async def test_waterleak_features(dev):
    """Test waterleak features."""
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]

    assert "water_leak" in dev.features
    assert dev.features["water_leak"].value == waterleak.status

    assert "water_alert" in dev.features
    assert dev.features["water_alert"].value == waterleak.alert
