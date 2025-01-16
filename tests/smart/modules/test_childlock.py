import pytest

from kasa import Module
from kasa.smart.modules import ChildLock

from ...device_fixtures import parametrize

childlock = parametrize(
    "has child lock",
    component_filter="button_and_led",
    protocol_filter={"SMART.CHILD"},
)


@childlock
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("child_lock", "enabled", bool),
    ],
)
async def test_features(dev, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    protect: ChildLock = dev.modules[Module.ChildLock]
    assert protect is not None

    prop = getattr(protect, prop_name)
    assert isinstance(prop, type)

    feat = protect._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@childlock
async def test_enabled(dev):
    """Test the API."""
    protect: ChildLock = dev.modules[Module.ChildLock]
    assert protect is not None

    assert isinstance(protect.enabled, bool)
    await protect.set_enabled(False)
    await dev.update()
    assert protect.enabled is False
