from typing import cast

import pytest

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules import ChildLock

from ...device_fixtures import parametrize

childlock = parametrize(
    "has child lock",
    component_filter="button_and_led",
    protocol_filter={"SMART"},
)


@childlock
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
    protect = cast(ChildLock, dev.modules[Module.ChildLock])
    assert protect is not None

    prop = getattr(protect, prop_name)
    assert isinstance(prop, type)

    feat = protect._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@childlock
async def test_enabled(dev: SmartDevice) -> None:
    """Test the API."""
    protect = cast(ChildLock, dev.modules[Module.ChildLock])
    assert protect is not None

    assert isinstance(protect.enabled, bool)
    await protect.set_enabled(False)
    await dev.update()
    assert protect.enabled is False
