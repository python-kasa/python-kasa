import pytest

from kasa import SmartDevice
from kasa.smart.modules import ContactSensor
from kasa.tests.device_fixtures import parametrize

contact = parametrize(
    "is contact sensor", model_filter="T110", protocol_filter={"SMART.CHILD"}
)


@contact
@pytest.mark.parametrize(
    "feature, type",
    [
        ("is_open", bool),
    ],
)
async def test_contact_features(dev: SmartDevice, feature, type):
    """Test that features are registered and work as expected."""
    contact = dev.get_module(ContactSensor)
    assert contact is not None

    prop = getattr(contact, feature)
    assert isinstance(prop, type)

    feat = contact._module_features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)
