from __future__ import annotations

import asyncio
import logging

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.smart.modules.firmware import DownloadState
from kasa.tests.device_fixtures import parametrize

firmware = parametrize(
    "has firmware", component_filter="firmware", protocol_filter={"SMART"}
)


@firmware
@pytest.mark.parametrize(
    "feature, prop_name, type, required_version",
    [
        ("auto_update_enabled", "auto_update_enabled", bool, 2),
        ("update_available", "update_available", bool, 1),
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

    if not dev.is_cloud_connected:
        pytest.skip("Device is not cloud connected, skipping test")

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

    if dev.is_cloud_connected:
        assert isinstance(fw.update_available, bool)
    else:
        assert fw.update_available is None


@firmware
async def test_firmware_update(
    dev: SmartDevice, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test updating firmware."""
    caplog.set_level(logging.INFO)

    fw = dev.modules.get(Module.Firmware)
    assert fw

    upgrade_time = 5
    extras = {"reboot_time": 5, "upgrade_time": upgrade_time, "auto_upgrade": False}
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

    await fw.update(progress_cb=cb_mock)

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
