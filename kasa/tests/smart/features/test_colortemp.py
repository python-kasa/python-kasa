import pytest

from kasa.smart import SmartDevice
from kasa.tests.conftest import variable_temp_smart


@variable_temp_smart
async def test_colortemp_component(dev: SmartDevice):
    """Test brightness feature."""
    assert isinstance(dev, SmartDevice)
    assert "color_temperature" in dev._components

    # Test getting the value
    feature = dev.features["color_temperature"]
    assert isinstance(feature.value, int)
    assert isinstance(feature.minimum_value, int)
    assert isinstance(feature.maximum_value, int)

    # Test setting the value
    # We need to take the min here, as L9xx reports a range [9000, 9000].
    new_value = min(feature.minimum_value + 1, feature.maximum_value)
    await feature.set_value(new_value)
    await dev.update()
    assert feature.value == new_value

    with pytest.raises(ValueError):
        await feature.set_value(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await feature.set_value(feature.maximum_value + 10)
