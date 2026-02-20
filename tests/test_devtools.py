"""Module for dump_devinfo tests."""

import copy

import pytest

from devtools.dump_devinfo import (
    _wrap_redactors,
    get_legacy_fixture,
    get_smart_fixtures,
)
from kasa.iot import IotDevice
from kasa.protocols import IotProtocol
from kasa.protocols.protocol import redact_data
from kasa.protocols.smartprotocol import REDACTORS as SMART_REDACTORS
from kasa.smart import SmartDevice
from kasa.smartcam import SmartCamDevice
from kasa.smartcam.smartcamchild import CHILD_INFO_FROM_PARENT

from .conftest import (
    FixtureInfo,
    get_device_for_fixture,
    get_fixture_info,
    parametrize,
)

smart_fixtures = parametrize(
    "smart fixtures", protocol_filter={"SMART"}, fixture_name="fixture_info"
)
smartcam_fixtures = parametrize(
    "smartcam fixtures", protocol_filter={"SMARTCAM"}, fixture_name="fixture_info"
)
iot_fixtures = parametrize(
    "iot fixtures", protocol_filter={"IOT"}, fixture_name="fixture_info"
)


async def test_fixture_names(fixture_info: FixtureInfo):
    """Test that device info gets the right fixture names."""
    if fixture_info.protocol in {"SMARTCAM"}:
        device_info = SmartCamDevice._get_device_info(
            fixture_info.data,
            fixture_info.data.get("discovery_result", {}).get("result"),
        )
    elif fixture_info.protocol in {"SMART"}:
        device_info = SmartDevice._get_device_info(
            fixture_info.data,
            fixture_info.data.get("discovery_result", {}).get("result"),
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
    """Test that smart fixtures are created the same."""
    dev = await get_device_for_fixture(fixture_info, verbatim=True)
    assert isinstance(dev, SmartDevice)
    if dev.children:
        pytest.skip("Test not currently implemented for devices with children.")
    fixtures = await get_smart_fixtures(
        dev.protocol,
        discovery_info=fixture_info.data.get("discovery_result"),
        batch_size=5,
    )
    fixture_result = fixtures[0]

    assert fixture_info.data == fixture_result.data


def _normalize_child_device_ids(info: dict):
    """Scrubbed child device ids in hubs may not match ids in child fixtures.

    Different hub fixtures could create the same child fixture so we scrub
    them again for the purpose of the test.
    """
    if dev_info := info.get("get_device_info"):
        dev_info["device_id"] = "SCRUBBED"
    elif (
        dev_info := info.get("getDeviceInfo", {})
        .get("device_info", {})
        .get("basic_info")
    ):
        dev_info["dev_id"] = "SCRUBBED"


@smartcam_fixtures
async def test_smartcam_fixtures(fixture_info: FixtureInfo):
    """Test that smartcam fixtures are created the same."""
    # Skip door locks as they have different module requirements
    if (
        fixture_info.data.get("discovery_result", {})
        .get("result", {})
        .get("device_type")
        == "SMART.TAPOLOCK"
    ):
        pytest.skip("Door lock fixtures have different requirements")

    dev = await get_device_for_fixture(fixture_info, verbatim=True)
    assert isinstance(dev, SmartCamDevice)

    created_fixtures = await get_smart_fixtures(
        dev.protocol,
        discovery_info=fixture_info.data.get("discovery_result"),
        batch_size=5,
    )
    fixture_result = created_fixtures.pop(0)

    assert fixture_info.data == fixture_result.data

    for created_child_fixture in created_fixtures:
        child_fixture_info = get_fixture_info(
            created_child_fixture.filename + ".json",
            created_child_fixture.protocol_suffix,
        )

        assert child_fixture_info

        _normalize_child_device_ids(created_child_fixture.data)

        saved_fixture_data = copy.deepcopy(child_fixture_info.data)
        _normalize_child_device_ids(saved_fixture_data)
        saved_fixture_data = {
            key: val for key, val in saved_fixture_data.items() if val != -1001
        }

        # Remove the child info from parent from the comparison because the
        # child may have been created by a different parent fixture
        saved_fixture_data.pop(CHILD_INFO_FROM_PARENT, None)
        created_cifp = created_child_fixture.data.pop(CHILD_INFO_FROM_PARENT, None)

        # Still check that the created child info from parent was redacted.
        # only smartcam children generate child_info_from_parent
        if created_cifp:
            redacted_cifp = redact_data(created_cifp, _wrap_redactors(SMART_REDACTORS))
            assert created_cifp == redacted_cifp

        assert saved_fixture_data == created_child_fixture.data


@iot_fixtures
async def test_iot_fixtures(fixture_info: FixtureInfo):
    """Test that iot fixtures are created the same."""
    # Iot fixtures often do not have enough data to perform a device update()
    # without missing info being added to suppress the update
    dev = await get_device_for_fixture(
        fixture_info, verbatim=True, update_after_init=False
    )
    assert isinstance(dev.protocol, IotProtocol)

    fixture = await get_legacy_fixture(
        dev.protocol, discovery_info=fixture_info.data.get("discovery_result")
    )
    fixture_result = fixture

    created_fixture = {
        key: val for key, val in fixture_result.data.items() if "err_code" not in val
    }
    saved_fixture = {
        key: val for key, val in fixture_info.data.items() if "err_code" not in val
    }
    assert saved_fixture == created_fixture
