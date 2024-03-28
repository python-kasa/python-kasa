import pytest

from kasa import FeatureNames
from kasa.iot import IotDevice
from kasa.smart import SmartDevice
from kasa.tests.conftest import dimmable, parametrize

brightness = parametrize("brightness smart", component_filter="brightness")


@brightness
async def test_brightness_component(dev: SmartDevice):
    """Test brightness feature."""
    assert isinstance(dev, SmartDevice)
    assert "brightness" in dev._components

    # Test getting the value
    feature = dev.features[FeatureNames.BRIGHTNESS]
    assert isinstance(feature.value, int)
    assert feature.value > 0 and feature.value <= 100

    # Test setting the value
    await feature.set_value(10)
    assert feature.value == 10

    with pytest.raises(ValueError):
        await feature.set_value(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await feature.set_value(feature.maximum_value + 10)


@dimmable
async def test_brightness_dimmable(dev: SmartDevice):
    """Test brightness feature."""
    assert isinstance(dev, IotDevice)
    assert "brightness" in dev.sys_info or bool(dev.sys_info["is_dimmable"])

    # Test getting the value
    feature = dev.features[FeatureNames.BRIGHTNESS]
    assert isinstance(feature.value, int)
    assert feature.value > 0 and feature.value <= 100

    # Test setting the value
    await feature.set_value(10)
    assert feature.value == 10

    with pytest.raises(ValueError):
        await feature.set_value(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await feature.set_value(feature.maximum_value + 10)
