import pytest

from kasa.smart.modules import ContactSensor
from kasa.tests.device_fixtures import parametrize

contact = parametrize(
    "has humidity", model_filter="T110", protocol_filter={"SMART.CHILD"}
)


@contact
@pytest.mark.parametrize(
    "feature, type",
    [
        ("is_open", bool),
    ],
)
async def test_contact_features(dev, feature, type):
    """Test that features are registered and work as expected."""
    contact: ContactSensor = dev.modules["ContactSensor"]

    prop = getattr(contact, feature)
    assert isinstance(prop, type)

    feat = contact._module_features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
