"""Tests for smart camera devices."""

from __future__ import annotations

from ..conftest import device_smartcamera


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
