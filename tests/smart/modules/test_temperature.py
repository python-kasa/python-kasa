from typing import cast

import pytest

from kasa.smart import SmartDevice
from kasa.smart.modules import TemperatureSensor

from ...device_fixtures import parametrize

temperature = parametrize(
    "has temperature", component_filter="temperature", protocol_filter={"SMART.CHILD"}
)

temperature_warning = parametrize(
    "has temperature warning",
    component_filter="comfort_temperature",
    protocol_filter={"SMART.CHILD"},
)


@temperature
@pytest.mark.parametrize(
    ("feature", "type"),
    [
        ("temperature", float),
        ("temperature_unit", str),
    ],
)
async def test_temperature_features(dev: SmartDevice, feature: str, type: type) -> None:
    """Test that features are registered and work as expected."""
    temp_module = cast(TemperatureSensor, dev.modules["TemperatureSensor"])

    prop = getattr(temp_module, feature)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@temperature_warning
async def test_temperature_warning(dev: SmartDevice) -> None:
    """Test that features are registered and work as expected."""
    temp_module = cast(TemperatureSensor, dev.modules["TemperatureSensor"])

    assert hasattr(temp_module, "temperature_warning")
    assert isinstance(temp_module.temperature_warning, bool)

    feat = dev.features["temperature_warning"]
    assert feat.value == temp_module.temperature_warning
    assert isinstance(feat.value, bool)
