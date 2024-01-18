import errno
import json
import logging
import secrets
import struct
import sys
import time
from contextlib import nullcontext as does_not_raise
from itertools import chain

import pytest

from ..aestransport import AesTransport
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    SMART_RETRYABLE_ERRORS,
    SMART_TIMEOUT_ERRORS,
    SmartDeviceException,
    SmartErrorCode,
)
from ..iotprotocol import IotProtocol
from ..klaptransport import KlapEncryptionSession, KlapTransport, _sha256
from ..smartprotocol import SmartProtocol

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}
ERRORS = [e for e in SmartErrorCode if e != 0]


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors(mocker, error_code):
    host = "127.0.0.1"
    mock_response = {"result": {"great": "success"}, "error_code": error_code.value}

    mocker.patch.object(AesTransport, "perform_handshake")
    mocker.patch.object(AesTransport, "perform_login")

    send_mock = mocker.patch.object(AesTransport, "send", return_value=mock_response)

    config = DeviceConfig(host, credentials=Credentials("foo", "bar"))
    protocol = SmartProtocol(transport=AesTransport(config=config))
    with pytest.raises(SmartDeviceException):
        await protocol.query(DUMMY_QUERY, retry_count=2)

    if error_code in chain(SMART_TIMEOUT_ERRORS, SMART_RETRYABLE_ERRORS):
        expected_calls = 3
    else:
        expected_calls = 1
    assert send_mock.call_count == expected_calls


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors_in_multiple_request(mocker, error_code):
    host = "127.0.0.1"
    mock_response = {
        "result": {
            "responses": [
                {"method": "foobar1", "result": {"great": "success"}, "error_code": 0},
                {
                    "method": "foobar2",
                    "result": {"great": "success"},
                    "error_code": error_code.value,
                },
                {"method": "foobar3", "result": {"great": "success"}, "error_code": 0},
            ]
        },
        "error_code": 0,
    }

    mocker.patch.object(AesTransport, "perform_handshake")
    mocker.patch.object(AesTransport, "perform_login")

    send_mock = mocker.patch.object(AesTransport, "send", return_value=mock_response)
    config = DeviceConfig(host, credentials=Credentials("foo", "bar"))
    protocol = SmartProtocol(transport=AesTransport(config=config))
    with pytest.raises(SmartDeviceException):
        await protocol.query(DUMMY_QUERY, retry_count=2)
    if error_code in chain(SMART_TIMEOUT_ERRORS, SMART_RETRYABLE_ERRORS):
        expected_calls = 3
    else:
        expected_calls = 1
    assert send_mock.call_count == expected_calls
