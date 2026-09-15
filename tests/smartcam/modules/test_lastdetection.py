"""Tests for smartcam last detection module."""

from __future__ import annotations

from datetime import datetime

import pytest

from kasa import Device
from kasa.smart import SmartDevice
from kasa.smartcam.smartcammodule import SmartCamModule

from ...device_fixtures import parametrize

lastdetection_smartcam = parametrize(
    "has last detection",
    component_filter="detection",
    protocol_filter={"SMARTCAM"},
)
lastdetection_hub_child = parametrize(
    "hub child with detection",
    component_filter="detection",
    protocol_filter={"SMARTCAM.CHILD"},
)


def _set_last_alarm_info(dev: Device, time: str, type_: str = "") -> None:
    dev._last_update["getLastAlarmInfo"]["system"]["last_alarm_info"] = {
        "last_alarm_time": time,
        "last_alarm_type": type_,
    }


@lastdetection_smartcam
async def test_last_detection_features(dev: Device) -> None:
    """Test that the module and its features are available."""
    last_detection = dev.modules.get(SmartCamModule.SmartCamLastDetection)
    assert last_detection

    for feat_id in ("last_detection_timestamp", "last_detection_type"):
        feat = dev.features.get(feat_id)
        assert feat
        assert feat.value == getattr(last_detection, feat_id)


@lastdetection_smartcam
async def test_last_detection_values(dev: Device) -> None:
    """Test that a reported detection is exposed as a timezone aware datetime."""
    last_detection = dev.modules.get(SmartCamModule.SmartCamLastDetection)
    assert last_detection
    _set_last_alarm_info(dev, "1734967724", "motion")

    detection_time = last_detection.last_detection_timestamp
    assert isinstance(detection_time, datetime)
    assert detection_time.tzinfo == dev.timezone
    assert detection_time.timestamp() == 1734967724
    assert last_detection.last_detection_type == "motion"


@lastdetection_smartcam
@pytest.mark.parametrize(
    "time_raw",
    [
        "",  # never triggered (C100)
        "0",  # never triggered (C110, C220, ...)
        "nonsense",  # unexpected value must not break feature access
        "99999999999999999",  # out of range for datetime.fromtimestamp
    ],
)
async def test_last_detection_never_triggered(dev: Device, time_raw: str) -> None:
    """Test that devices that never detected anything report None."""
    last_detection = dev.modules.get(SmartCamModule.SmartCamLastDetection)
    assert last_detection

    _set_last_alarm_info(dev, time_raw)

    assert last_detection.last_detection_timestamp is None
    assert last_detection.last_detection_type is None


@lastdetection_hub_child
async def test_last_detection_not_exposed_on_hub_children(dev: Device) -> None:
    """Test that hub children do not expose the module.

    Hub child modules are only refreshed once a day, which defeats the purpose
    of polling the last detection.
    """
    assert isinstance(dev, SmartDevice)
    assert dev._is_hub_child
    assert SmartCamModule.SmartCamLastDetection not in dev.modules
    assert "last_detection_timestamp" not in dev.features
    assert "last_detection_type" not in dev.features
