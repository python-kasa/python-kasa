"""Tests for SmartIrAC."""

from unittest.mock import AsyncMock

import pytest

from kasa.device_type import DeviceType
from kasa.smart.smartdevice import SmartDevice
from kasa.smart.smartirac import SmartIrAC


@pytest.fixture
def ac_info():
    """Return child AC info."""
    return {
        "device_id": "12345",
        "category": "ir.remote",
        "model": "AC",
        "ac_status": "P1_M1_T24_S1_D0",
    }


@pytest.fixture
def ac_components():
    """Return AC components."""
    return {"component_list": [{"id": "device", "ver_code": 1}]}


async def test_smartirac_init(ac_info, ac_components):
    """Test initializing SmartIrAC."""
    parent = SmartDevice("127.0.0.1")
    device = await SmartIrAC.create(parent, ac_info, ac_components)

    try:
        assert device.device_type == DeviceType.Climate
    except AttributeError:
        assert device.device_type == DeviceType.Thermostat

    assert device.is_on is True
    assert device.target_temperature == 24
    assert device.hvac_mode == 1
    assert device.fan_mode == 1
    assert device.swing_mode == 0


async def test_smartirac_turn_off(ac_info, ac_components):
    """Test turning off the AC."""
    parent = SmartDevice("127.0.0.1")
    device = await SmartIrAC.create(parent, ac_info, ac_components)

    device.protocol = AsyncMock()
    device.protocol.query.return_value = {"sendIrCmdByStatus": None}

    assert device.is_on is True

    await device.turn_off()

    assert device.is_on is False
    device.protocol.query.assert_called_once()

    # Check payload structure
    request = device.protocol.query.call_args[0][0]
    assert "multipleRequest" in request
    requests = request["multipleRequest"]["requests"]
    assert len(requests) == 1
    assert requests[0]["method"] == "sendIrCmdByStatus"
    assert requests[0]["params"]["power"] is False
    assert requests[0]["params"]["on"] is False


async def test_smartirac_set_temperature(ac_info, ac_components):
    """Test setting target temperature."""
    parent = SmartDevice("127.0.0.1")
    device = await SmartIrAC.create(parent, ac_info, ac_components)

    device.protocol = AsyncMock()
    device.protocol.query.return_value = {"sendIrCmdByStatus": None}

    assert device.target_temperature == 24

    await device.set_target_temperature(20)

    assert device.target_temperature == 20
    device.protocol.query.assert_called_once()

    request = device.protocol.query.call_args[0][0]
    requests = request["multipleRequest"]["requests"]
    assert requests[0]["params"]["temp"] == 20
