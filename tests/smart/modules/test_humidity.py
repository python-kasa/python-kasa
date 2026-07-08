import pytest

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

humidity = parametrize(
    "has humidity", component_filter="humidity", protocol_filter={"SMART.CHILD"}
)


@humidity
@pytest.mark.parametrize(
    ("feature", "type"),
    [
        ("humidity", int),
        ("humidity_warning", bool),
    ],
)
async def test_humidity_features(dev: SmartDevice, feature: str, type: type) -> None:
    """Test that features are registered and work as expected."""
    humidity = dev.modules[Module.HumiditySensor]

    prop = getattr(humidity, feature)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
