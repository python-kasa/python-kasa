"""Tests for smart camera devices."""

from __future__ import annotations

import pytest

from kasa import Device
from kasa.smartcam.modules.alarm import (
    DURATION_MAX,
    DURATION_MIN,
    VOLUME_MAX,
    VOLUME_MIN,
)
from kasa.smartcam.smartcammodule import SmartCamModule

from ...conftest import hub_smartcam


@hub_smartcam
async def test_alarm(dev: Device):
    """Test device alarm."""
    alarm = dev.modules.get(SmartCamModule.SmartCamAlarm)
    assert alarm

    original_duration = alarm.alarm_duration
    assert original_duration is not None
    original_volume = alarm.alarm_volume
    assert original_volume is not None
    original_sound = alarm.alarm_sound

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

        # test start
        await alarm.play()
        await dev.update()
        assert alarm.active

        # test stop
        await alarm.stop()
        await dev.update()
        assert not alarm.active

        # test set sound
        new_sound = (
            alarm.alarm_sounds[0]
            if alarm.alarm_sound != alarm.alarm_sounds[0]
            else alarm.alarm_sounds[1]
        )
        await alarm.set_alarm_sound(new_sound)
        await dev.update()
        assert alarm.alarm_sound == new_sound

    finally:
        await alarm.set_alarm_volume(original_volume)
        await alarm.set_alarm_duration(original_duration)
        await alarm.set_alarm_sound(original_sound)
        await dev.update()


@hub_smartcam
async def test_alarm_invalid_setters(dev: Device):
    """Test device alarm invalid setter values."""
    alarm = dev.modules.get(SmartCamModule.SmartCamAlarm)
    assert alarm

    # test set sound invalid
    msg = f"sound must be one of {', '.join(alarm.alarm_sounds)}: foobar"
    with pytest.raises(ValueError, match=msg):
        await alarm.set_alarm_sound("foobar")

    # test volume invalid
    msg = f"volume must be between {VOLUME_MIN} and {VOLUME_MAX}"
    with pytest.raises(ValueError, match=msg):
        await alarm.set_alarm_volume(-3)

    # test duration invalid
    msg = f"duration must be between {DURATION_MIN} and {DURATION_MAX}"
    with pytest.raises(ValueError, match=msg):
        await alarm.set_alarm_duration(-3)


@hub_smartcam
async def test_alarm_features(dev: Device):
    """Test device alarm features."""
    alarm = dev.modules.get(SmartCamModule.SmartCamAlarm)
    assert alarm

    original_duration = alarm.alarm_duration
    assert original_duration is not None
    original_volume = alarm.alarm_volume
    assert original_volume is not None
    original_sound = alarm.alarm_sound

    try:
        # test volume
        new_volume = original_volume - 1 if original_volume > 1 else original_volume + 1
        feature = dev.features.get("alarm_volume")
        assert feature
        await feature.set_value(new_volume)  # type: ignore[arg-type]
        await dev.update()
        assert feature.value == new_volume

        # test duration
        feature = dev.features.get("alarm_duration")
        assert feature
        new_duration = (
            original_duration - 1 if original_duration > 1 else original_duration + 1
        )
        await feature.set_value(new_duration)
        await dev.update()
        assert feature.value == new_duration

        # test start
        feature = dev.features.get("test_alarm")
        assert feature
        await feature.set_value(None)
        await dev.update()
        feature = dev.features.get("alarm")
        assert feature
        assert feature.value is True

        # test stop
        feature = dev.features.get("stop_alarm")
        assert feature
        await feature.set_value(None)
        await dev.update()
        assert dev.features["alarm"].value is False

        # test set sound
        feature = dev.features.get("alarm_sound")
        assert feature
        new_sound = (
            alarm.alarm_sounds[0]
            if alarm.alarm_sound != alarm.alarm_sounds[0]
            else alarm.alarm_sounds[1]
        )
        await feature.set_value(new_sound)
        await alarm.set_alarm_sound(new_sound)
        await dev.update()
        assert feature.value == new_sound

    finally:
        await alarm.set_alarm_volume(original_volume)
        await alarm.set_alarm_duration(original_duration)
        await alarm.set_alarm_sound(original_sound)
        await dev.update()
