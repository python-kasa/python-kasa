"""Tests for smart camera devices."""

from __future__ import annotations

import pytest

from kasa import Device, DeviceType

from ..conftest import device_smartcamera


@device_smartcamera
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    state = dev.is_on
    await dev.set_state(not state)
    await dev.update()
    assert dev.is_on is not state
