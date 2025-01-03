"""Tests for smart camera devices."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Device, DeviceType, Module

from ..conftest import device_smartcam, hub_smartcam


@device_smartcam
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    if Module.LensMask in dev.modules:
        state = dev.is_on
        await dev.set_state(not state)
        await dev.update()
        assert dev.is_on is not state

        dev.modules.pop(Module.LensMask)  # type: ignore[attr-defined]

    # Test with no lens mask module. Device is always on.
    assert dev.is_on is True
    res = await dev.set_state(False)
    assert res == {}
    await dev.update()
    assert dev.is_on is True


@device_smartcam
async def test_alias(dev):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    await dev.update()
    assert dev.alias == test_alias

    await dev.set_alias(original)
    await dev.update()
    assert dev.alias == original


@hub_smartcam
async def test_hub(dev):
    assert dev.children
    for child in dev.children:
        assert child.modules

        assert child.alias
        await child.update()
        assert child.device_id


@device_smartcam
async def test_device_time(dev: Device, freezer: FrozenDateTimeFactory):
    """Test a child device gets the time from it's parent module."""
    fallback_time = datetime.now(UTC).astimezone().replace(microsecond=0)
    assert dev.time != fallback_time
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.time == fallback_time
