from kasa.device import Device
from kasa.feature import Feature
from kasa.smart import SmartDevice
from kasa.tests.conftest import (
    device_iot,
    device_smart,
    has_children_smart,
    parametrize_combine,
    parametrize_subtract,
)

control_state = parametrize_combine(
    [device_iot, parametrize_subtract(device_smart, has_children_smart)]
)


@control_state
async def test_feature_state(dev: Device):
    """Test brightness feature."""
    if isinstance(dev, SmartDevice):
        assert "device_on" in dev._info

    assert dev.has_feature(Feature.state) is True
    assert isinstance(dev[Feature.state].value, bool)

    await dev[Feature.state].set_value(True)
    assert dev[Feature.state].value is True

    await dev[Feature.state].set_value(False)
    assert dev[Feature.state].value is False
