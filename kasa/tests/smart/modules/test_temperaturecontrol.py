import pytest

from kasa.smart.modules import TemperatureSensor
from kasa.tests.device_fixtures import parametrize

temperature = parametrize(
    "has temperature control",
    component_filter="temperature_control",
    protocol_filter={"SMART.CHILD"},
)


@temperature
@pytest.mark.parametrize(
    "feature, type",
    [
        ("target_temperature", int),
        ("temperature_offset", int),
    ],
)
async def test_temperature_control_features(dev, feature, type):
    """Test that features are registered and work as expected."""
    temp_module: TemperatureSensor = dev.modules["TemperatureControl"]

    prop = getattr(temp_module, feature)
    assert isinstance(prop, type)

    feat = temp_module._module_features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)

    await feat.set_value(10)
    await dev.update()
    assert feat.value == 10
