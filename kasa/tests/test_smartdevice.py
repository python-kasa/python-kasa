"""Tests for SMART devices."""
import logging
from unittest.mock import patch

import pytest  # type: ignore # https://github.com/pytest-dev/pytest/issues/3342

from kasa import KasaException
from kasa.exceptions import SmartErrorCode
from kasa.smart import SmartDevice

from .conftest import (
    device_smart,
)


@device_smart
async def test_try_get_response(dev: SmartDevice, caplog):
    mock_response: dict = {
        "get_device_info": SmartErrorCode.PARAMS_ERROR,
    }
    caplog.set_level(logging.DEBUG)
    dev._try_get_response(mock_response, "get_device_info", {})
    msg = "Error PARAMS_ERROR(-1008) getting request get_device_info for device 127.0.0.123"
    assert msg in caplog.text


@device_smart
async def test_update_no_device_info(dev: SmartDevice):
    mock_response: dict = {
        "get_device_usage": {},
        "get_device_time": {},
    }
    msg = f"get_device_info not found in {mock_response} for device 127.0.0.123"
    with patch.object(dev.protocol, "query", return_value=mock_response), pytest.raises(
        KasaException, match=msg
    ):
        await dev.update()
