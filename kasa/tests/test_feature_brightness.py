from kasa.smart import SmartDevice
from kasa.tests.conftest import parametrize

brightness = parametrize("brightness smart", component_filter="brightness")


@brightness
async def test_brightness_component(dev: SmartDevice):
    """Test brightness feature."""
    assert isinstance(dev, SmartDevice)
    assert "brightness" in dev._components

    # Test getting the value
    feature = dev.features["brightness"]
    assert isinstance(feature.value, int)
    assert feature.value > 0 and feature.value <= 100

    # Test setting the value
    await feature.set_value(10)
    assert feature.value == 10
