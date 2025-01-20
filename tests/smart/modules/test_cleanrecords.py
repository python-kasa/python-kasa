from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import get_parent_and_child_modules, parametrize

cleanrecords = parametrize(
    "has clean records", component_filter="clean_percent", protocol_filter={"SMART"}
)


@cleanrecords
@pytest.mark.parametrize(
    ("feature", "prop_name", "type"),
    [
        ("total_clean_area", "total_clean_area", int),
        ("total_clean_time", "total_clean_time", timedelta),
        ("last_clean_area", "last_clean_area", int),
        ("last_clean_time", "last_clean_time", timedelta),
        ("total_clean_count", "total_clean_count", int),
        ("last_clean_timestamp", "last_clean_timestamp", datetime),
    ],
)
async def test_features(dev: SmartDevice, feature: str, prop_name: str, type: type):
    """Test that features are registered and work as expected."""
    records = next(get_parent_and_child_modules(dev, Module.CleanRecords))
    assert records is not None

    prop = getattr(records, prop_name)
    assert isinstance(prop, type)

    feat = records._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@cleanrecords
async def test_timezone(dev: SmartDevice):
    """Test that timezone is added to timestamps."""
    clean_records = next(get_parent_and_child_modules(dev, Module.CleanRecords))
    assert clean_records is not None

    assert isinstance(clean_records.last_clean_timestamp, datetime)
    assert clean_records.last_clean_timestamp.tzinfo

    # Check for zone info to ensure that this wasn't picking upthe default
    # of utc before the time module is updated.
    assert isinstance(clean_records.last_clean_timestamp.tzinfo, ZoneInfo)

    for record in clean_records.parsed_data.records:
        assert isinstance(record.timestamp, datetime)
        assert record.timestamp.tzinfo
        assert isinstance(record.timestamp.tzinfo, ZoneInfo)
