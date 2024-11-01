import pytest

from kasa import Module
from kasa.smart.modules import ChildProtection
from kasa.tests.device_fixtures import parametrize

child_protection = parametrize(
    "has child protection",
    component_filter="child_protection",
    protocol_filter={"SMART.CHILD"},
)


@child_protection
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("child_lock", "enabled", bool),
    ],
)
async def test_features(dev, feature, prop_name, type):
    """Test that features are registered and work as expected."""
    protect: ChildProtection = dev.modules[Module.ChildProtection]
    assert protect is not None

    prop = getattr(protect, prop_name)
    assert isinstance(prop, type)

    feat = protect._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@child_protection
async def test_enabled(dev):
    """Test the API."""
    protect: ChildProtection = dev.modules[Module.ChildProtection]
    assert protect is not None

    assert isinstance(protect.enabled, bool)
    await protect.set_enabled(False)
    await dev.update()
    assert protect.enabled is False
