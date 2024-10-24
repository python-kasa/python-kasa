"""Tests for smart camera devices."""

from __future__ import annotations

import pytest

from kasa import Device, DeviceType

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
