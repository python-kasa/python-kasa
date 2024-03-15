import pytest

from kasa.smart.modules import TemperatureSensor
from kasa.tests.device_fixtures import parametrize

temperature = parametrize(
    "has temperature", component_filter="temperature", protocol_filter={"SMART.CHILD"}
)


@temperature
@pytest.mark.parametrize(
    "feature, type",
    [
        ("temperature", float),
        ("temperature_warning", bool),
        ("temperature_unit", str),
    ],
)
async def test_temperature_features(dev, feature, type):
    """Test that features are registered and work as expected."""
    temp_module: TemperatureSensor = dev.modules["TemperatureSensor"]

    prop = getattr(temp_module, feature)
    assert isinstance(prop, type)

    feat = temp_module._module_features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
