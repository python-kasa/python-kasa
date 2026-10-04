"""Tests for smartcam last alert detection module."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from kasa import Device
from kasa.smart import SmartDevice
from kasa.smartcam.modules.lastalertdetection import (
    LastAlertDetection,
    LastAlertType,
)
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

lastalertdetection_smartcam = parametrize(
    "has last alert detection",
    component_filter="detection",
    protocol_filter={"SMARTCAM"},
)
lastalertdetection_hub_child = parametrize(
    "hub child with detection",
    component_filter="detection",
    protocol_filter={"SMARTCAM.CHILD"},
)


def _set_last_alarm_info(dev: Device, time: str, type_: str = "") -> None:
    dev._last_update["getLastAlarmInfo"]["system"]["last_alarm_info"] = {
        "last_alarm_time": time,
        "last_alarm_type": type_,
    }


@lastalertdetection_smartcam
async def test_last_alert_features(dev: Device) -> None:
    """Test that the module and its features are available."""
    last_alert = dev.modules.get(SmartCamModule.SmartCamLastAlertDetection)
    assert last_alert

    for feat_id in ("last_alert_timestamp", "last_alert_type"):
        feat = dev.features.get(feat_id)
        assert feat
        assert feat.value == getattr(last_alert, feat_id)


@lastalertdetection_smartcam
async def test_last_alert_values(dev: Device) -> None:
    """Test that a reported alert is exposed as a tz-aware datetime and an enum."""
    last_alert = dev.modules.get(SmartCamModule.SmartCamLastAlertDetection)
    assert last_alert
    _set_last_alarm_info(dev, "1734967724", "motion")

    alert_time = last_alert.last_alert_timestamp
    assert isinstance(alert_time, datetime)
    assert alert_time.tzinfo == dev.timezone
    assert alert_time.timestamp() == 1734967724
    assert last_alert.last_alert_type is LastAlertType.Motion
    assert dev.features["last_alert_type"].value is LastAlertType.Motion


@lastalertdetection_smartcam
async def test_last_alert_type_unknown_logs_once(
    dev: Device, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that an unknown alert type falls back to Unknown with a single warning."""
    last_alert = dev.modules.get(SmartCamModule.SmartCamLastAlertDetection)
    assert last_alert
    caplog.set_level(logging.WARNING)
    # The warned-once set is process-wide, reset it so each fixture starts clean.
    LastAlertDetection._logged_unknown_types.clear()

    _set_last_alarm_info(dev, "1734967724", "vehicle")
    assert last_alert.last_alert_type is LastAlertType.Unknown
    assert "Unknown alert type" in caplog.text
    assert "vehicle" in caplog.text

    caplog.clear()
    assert last_alert.last_alert_type is LastAlertType.Unknown
    assert "Unknown alert type" not in caplog.text

    _set_last_alarm_info(dev, "1734967724", "person")
    assert last_alert.last_alert_type is LastAlertType.Unknown
    assert "person" in caplog.text


@lastalertdetection_smartcam
@pytest.mark.parametrize(
    "time_raw",
    [
        "",  # never triggered (C100)
        "0",  # never triggered (C110, C220, ...)
        "nonsense",  # unexpected value must not break feature access
        "99999999999999999",  # out of range for datetime.fromtimestamp
    ],
)
async def test_last_alert_never_triggered(dev: Device, time_raw: str) -> None:
    """Test that devices that never reported an alert return None."""
    last_alert = dev.modules.get(SmartCamModule.SmartCamLastAlertDetection)
    assert last_alert

    _set_last_alarm_info(dev, time_raw)

    assert last_alert.last_alert_timestamp is None
    assert last_alert.last_alert_type is None


@lastalertdetection_hub_child
async def test_last_alert_not_exposed_on_hub_children(dev: Device) -> None:
    """Test that hub children do not expose the module.

    Hub child modules are only refreshed once a day, which defeats the purpose
    of polling the last alert.
    """
    assert isinstance(dev, SmartDevice)
    assert dev._is_hub_child
    assert SmartCamModule.SmartCamLastAlertDetection not in dev.modules
    assert "last_alert_timestamp" not in dev.features
    assert "last_alert_type" not in dev.features
