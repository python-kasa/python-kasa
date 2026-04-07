from typing import cast

import pytest

from kasa.smart import SmartDevice
from kasa.smart.modules import HumiditySensor

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
    humidity = cast(HumiditySensor, dev.modules["HumiditySensor"])

    prop = getattr(humidity, feature)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
