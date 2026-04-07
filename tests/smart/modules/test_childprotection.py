from typing import cast

import pytest

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules import ChildProtection

from ...device_fixtures import parametrize

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
async def test_features(
    dev: SmartDevice, feature: str, prop_name: str, type: type
) -> None:
    """Test that features are registered and work as expected."""
    protect = cast(ChildProtection, dev.modules[Module.ChildProtection])
    assert protect is not None

    prop = getattr(protect, prop_name)
    assert isinstance(prop, type)

    feat = protect._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@child_protection
async def test_enabled(dev: SmartDevice) -> None:
    """Test the API."""
    protect = cast(ChildProtection, dev.modules[Module.ChildProtection])
    assert protect is not None

    assert isinstance(protect.enabled, bool)
    await protect.set_enabled(False)
    await dev.update()
    assert protect.enabled is False
