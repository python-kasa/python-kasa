"""Module for dump_devinfo tests."""

import pytest

from devtools.dump_devinfo import get_legacy_fixture, get_smart_fixtures
from kasa.iot import IotDevice
from kasa.smart import SmartDevice
from kasa.smartcamera import SmartCamera

from .conftest import (
    FixtureInfo,
    get_device_for_fixture,
    parametrize,
)

smart_fixtures = parametrize(
    "smart fixtures", protocol_filter={"SMART"}, fixture_name="fixture_info"
)
smartcamera_fixtures = parametrize(
    "smartcamera fixtures", protocol_filter={"SMARTCAMERA"}, fixture_name="fixture_info"
)
iot_fixtures = parametrize(
    "iot fixtures", protocol_filter={"IOT"}, fixture_name="fixture_info"
)


async def test_fixture_names(fixture_info: FixtureInfo):
    """Test that device info gets the right fixture names."""
    if fixture_info.protocol in {"SMARTCAMERA"}:
        device_info = SmartCamera._get_device_info(
            fixture_info.data, fixture_info.data.get("discovery_result")
        )
    elif fixture_info.protocol in {"SMART"}:
        device_info = SmartDevice._get_device_info(
            fixture_info.data, fixture_info.data.get("discovery_result")
        )
    elif fixture_info.protocol in {"SMART.CHILD"}:
        device_info = SmartDevice._get_device_info(fixture_info.data, None)
    else:
        device_info = IotDevice._get_device_info(fixture_info.data, None)

    region = f"({device_info.region})" if device_info.region else ""
    expected = f"{device_info.long_name}{region}_{device_info.hardware_version}_{device_info.firmware_version}.json"
    assert fixture_info.name == expected


@smart_fixtures
async def test_smart_fixtures(fixture_info: FixtureInfo):
    """Test that device info gets the right fixture names."""
    dev = await get_device_for_fixture(fixture_info, verbatim=True)
    assert isinstance(dev, SmartDevice)
    if dev.children:
        pytest.skip("Test not currently implemented for devices with children.")
    fixtures = await get_smart_fixtures(
        dev.protocol,
        discovery_info=fixture_info.data.get("discovery_result"),
        batch_size=5,
    )
    fixture_result = fixtures[0][2]

    assert fixture_info.data == fixture_result


@smartcamera_fixtures
async def test_smartcamera_fixtures(fixture_info: FixtureInfo):
    """Test that device info gets the right fixture names."""
    dev = await get_device_for_fixture(fixture_info, verbatim=True)
    assert isinstance(dev, SmartCamera)
    if dev.children:
        pytest.skip("Test not currently implemented for devices with children.")
    fixtures = await get_smart_fixtures(
        dev.protocol,
        discovery_info=fixture_info.data.get("discovery_result"),
        batch_size=5,
    )
    fixture_result = fixtures[0][2]

    assert fixture_info.data == fixture_result


@iot_fixtures
async def test_iot_fixtures(fixture_info: FixtureInfo):
    """Test that device info gets the right fixture names."""
    dev = await get_device_for_fixture(fixture_info, verbatim=True, update=False)

    fixture = await get_legacy_fixture(
        dev.protocol, discovery_info=fixture_info.data.get("discovery_result")
    )
    fixture_result = fixture[2]

    fixture_result = {
        key: val for key, val in fixture_result.items() if "err_code" not in val
    }
    saved_fixture = {
        key: val for key, val in fixture_info.data.items() if "err_code" not in val
    }
    assert saved_fixture == fixture_result
