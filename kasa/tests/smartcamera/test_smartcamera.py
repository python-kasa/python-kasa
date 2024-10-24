"""Tests for smart camera devices."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Device, DeviceType, Module

from ..conftest import device_smartcamera, hub_smartcamera


@device_smartcamera
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    state = dev.is_on
    await dev.set_state(not state)
    await dev.update()
    assert dev.is_on is not state


@device_smartcamera
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


@hub_smartcamera
async def test_hub(dev):
    assert dev.children
    for child in dev.children:
        assert "Cloud" in child.modules
        assert child.modules["Cloud"].data
        assert child.alias
        await child.update()
        assert "Time" not in child.modules
        assert child.time


@device_smartcamera
async def test_device_time(dev: Device, freezer: FrozenDateTimeFactory):
    """Test a child device gets the time from it's parent module."""
    fallback_time = datetime.now(timezone.utc).astimezone().replace(microsecond=0)
    assert dev.time != fallback_time
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.time == fallback_time
