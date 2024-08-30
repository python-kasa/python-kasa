from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from typing import TypedDict

import pytest
from pytest_mock import MockerFixture

from kasa import KasaException, Module
from kasa.smart import SmartDevice
from kasa.smart.modules.firmware import DownloadState
from kasa.tests.device_fixtures import parametrize

firmware = parametrize(
    "has firmware", component_filter="firmware", protocol_filter={"SMART"}
)


@firmware
@pytest.mark.parametrize(
    ("feature", "prop_name", "type", "required_version"),
    [
        ("auto_update_enabled", "auto_update_enabled", bool, 2),
        ("update_available", "update_available", bool, 1),
        ("current_firmware_version", "current_firmware", str, 1),
        ("available_firmware_version", "latest_firmware", str, 1),
    ],
)
async def test_firmware_features(
    dev: SmartDevice, feature, prop_name, type, required_version, mocker: MockerFixture
):
    """Test light effect."""
    fw = dev.modules.get(Module.Firmware)
    assert fw
    assert fw.firmware_update_info is None

    if not dev.is_cloud_connected:
        pytest.skip("Device is not cloud connected, skipping test")

    await fw.check_latest_firmware()
    if fw.supported_version < required_version:
        pytest.skip("Feature %s requires newer version" % feature)

    prop = getattr(fw, prop_name)
    assert isinstance(prop, type)

    feat = dev.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@firmware
async def test_update_available_without_cloud(dev: SmartDevice):
    """Test that update_available returns None when disconnected."""
    fw = dev.modules.get(Module.Firmware)
    assert fw
    assert fw.firmware_update_info is None

    if dev.is_cloud_connected:
        await fw.check_latest_firmware()
        assert isinstance(fw.update_available, bool)
    else:
        assert fw.update_available is None


@firmware
@pytest.mark.parametrize(
    ("update_available", "expected_result"),
    [
        pytest.param(True, nullcontext(), id="available"),
        pytest.param(False, pytest.raises(KasaException), id="not-available"),
    ],
)
async def test_firmware_update(
    dev: SmartDevice,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    update_available,
    expected_result,
):
    """Test updating firmware."""
    caplog.set_level(logging.INFO)

    if not dev.is_cloud_connected:
        pytest.skip("Device is not cloud connected, skipping test")

    fw = dev.modules.get(Module.Firmware)
    assert fw

    upgrade_time = 5

    class Extras(TypedDict):
        reboot_time: int
        upgrade_time: int
        auto_upgrade: bool

    extras: Extras = {
        "reboot_time": 5,
        "upgrade_time": upgrade_time,
        "auto_upgrade": False,
    }
    update_states = [
        # Unknown 1
        DownloadState(status=1, download_progress=0, **extras),
        # Downloading
        DownloadState(status=2, download_progress=10, **extras),
        DownloadState(status=2, download_progress=100, **extras),
        # Flashing
        DownloadState(status=3, download_progress=100, **extras),
        DownloadState(status=3, download_progress=100, **extras),
        # Done
        DownloadState(status=0, download_progress=100, **extras),
    ]

    asyncio_sleep = asyncio.sleep
    sleep = mocker.patch("asyncio.sleep")
    mocker.patch.object(fw, "get_update_state", side_effect=update_states)

    cb_mock = mocker.AsyncMock()

    assert fw.firmware_update_info is None
    with pytest.raises(KasaException):
        await fw.update(progress_cb=cb_mock)
    await fw.check_latest_firmware()
    assert fw.firmware_update_info is not None

    fw._firmware_update_info.status = 1 if update_available else 0

    with expected_result:
        await fw.update(progress_cb=cb_mock)

    if not update_available:
        return

    # This is necessary to allow the eventloop to process the created tasks
    await asyncio_sleep(0)

    assert "Unhandled state code" in caplog.text
    assert "Downloading firmware, progress: 10" in caplog.text
    assert "Flashing firmware, sleeping" in caplog.text
    assert "Update idle" in caplog.text

    for state in update_states:
        cb_mock.assert_any_await(state)

    # sleep based on the upgrade_time
    sleep.assert_any_call(upgrade_time)
