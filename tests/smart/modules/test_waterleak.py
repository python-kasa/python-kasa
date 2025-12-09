from datetime import datetime
from enum import Enum

import pytest

from kasa.smart.modules import WaterleakSensor

from ...conftest import get_device_for_fixture_protocol
from ...device_fixtures import parametrize

waterleak = parametrize(
    "has waterleak", component_filter="sensor_alarm", protocol_filter={"SMART.CHILD"}
)


@pytest.fixture
async def parent(request):
    """Get a dummy parent for tz tests."""
    return await get_device_for_fixture_protocol("H100(EU)_1.0_1.5.5.json", "SMART")


@waterleak
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("water_alert", "alert", int),
        ("water_alert_timestamp", "alert_timestamp", datetime | None),
        ("water_leak", "status", Enum),
    ],
)
async def test_waterleak_properties(dev, parent, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    dev._parent = parent
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]

    prop = getattr(waterleak, prop_name)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@waterleak
async def test_waterleak_features(dev, parent):
    """Test waterleak features."""
    dev._parent = parent
    waterleak: WaterleakSensor = dev.modules["WaterleakSensor"]

    assert "water_leak" in dev.features
    assert dev.features["water_leak"].value == waterleak.status

    assert "water_alert" in dev.features
    assert dev.features["water_alert"].value == waterleak.alert

    assert "water_alert_timestamp" in dev.features
    assert dev.features["water_alert_timestamp"].value == waterleak.alert_timestamp
