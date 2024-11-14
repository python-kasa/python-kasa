"""Tests for smart camera devices."""

from __future__ import annotations

from kasa import Device
from kasa.smartcamera.smartcameramodule import SmartCameraModule

from ...conftest import hub_smartcamera


@hub_smartcamera
async def test_alarm(dev: Device):
    """Test device alarm."""
    alarm = dev.modules.get(SmartCameraModule.SmartCameraAlarm)

    assert alarm
    original_duration = alarm.alarm_duration
    assert original_duration is not None
    original_volume = alarm.alarm_volume
    assert original_volume is not None

    try:
        # test volume
        new_volume = original_volume - 1 if original_volume > 1 else original_volume + 1
        await alarm.set_alarm_volume(new_volume)  # type: ignore[arg-type]
        await dev.update()
        assert alarm.alarm_volume == new_volume

        # test duration
        new_duration = (
            original_duration - 1 if original_duration > 1 else original_duration + 1
        )
        await alarm.set_alarm_duration(new_duration)
        await dev.update()
        assert alarm.alarm_duration == new_duration

    finally:
        await alarm.set_alarm_volume(original_volume)
        await alarm.set_alarm_duration(original_duration)
        await dev.update()
