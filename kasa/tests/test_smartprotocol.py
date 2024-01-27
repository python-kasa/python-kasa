import errno
import json
import logging
import secrets
import struct
import sys
import time
from contextlib import nullcontext as does_not_raise
from itertools import chain
from typing import Dict

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
DUMMY_MULTIPLE_QUERY = {
    "foobar": {"foo": "bar", "bar": "foo"},
    "barfoo": {"foo": "bar", "bar": "foo"},
}
ERRORS = [e for e in SmartErrorCode if e != 0]


# TODO: this could be moved to conftest to make it available for other tests?
@pytest.fixture()
def dummy_protocol():
    """Return a smart protocol instance with a mocking-ready dummy transport."""
    from kasa.protocol import BaseTransport

    class DummyTransport(BaseTransport):
        @property
        def default_port(self) -> int:
            return -1

        @property
        def credentials_hash(self) -> str:
            return "dummy hash"

        async def send(self, request: str) -> Dict:
            return {}

        async def close(self) -> None:
            pass

        async def reset(self) -> None:
            pass

    transport = DummyTransport(config=DeviceConfig(host="127.0.0.123"))
    protocol = SmartProtocol(transport=transport)

    return protocol


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors(dummy_protocol, mocker, error_code):
    mock_response = {"result": {"great": "success"}, "error_code": error_code.value}

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )

    with pytest.raises(SmartDeviceException):
        await dummy_protocol.query(DUMMY_QUERY, retry_count=2)

    if error_code in chain(SMART_TIMEOUT_ERRORS, SMART_RETRYABLE_ERRORS):
        expected_calls = 3
    else:
        expected_calls = 1
    assert send_mock.call_count == expected_calls


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors_in_multiple_request(
    dummy_protocol, mocker, error_code
):
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

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )
    with pytest.raises(SmartDeviceException):
        await dummy_protocol.query(DUMMY_MULTIPLE_QUERY, retry_count=2)
    if error_code in chain(SMART_TIMEOUT_ERRORS, SMART_RETRYABLE_ERRORS):
        expected_calls = 3
    else:
        expected_calls = 1
    assert send_mock.call_count == expected_calls


@pytest.mark.parametrize("request_size", [1, 3, 5, 10])
@pytest.mark.parametrize("batch_size", [1, 2, 3, 4, 5])
async def test_smart_device_multiple_request(mocker, request_size, batch_size):
    host = "127.0.0.1"
    requests = {}
    mock_response = {
        "result": {"responses": []},
        "error_code": 0,
    }
    for i in range(request_size):
        method = f"get_method_{i}"
        requests[method] = {"foo": "bar", "bar": "foo"}
        mock_response["result"]["responses"].append(
            {"method": method, "result": {"great": "success"}, "error_code": 0}
        )

    mocker.patch.object(AesTransport, "perform_handshake")
    mocker.patch.object(AesTransport, "perform_login")

    send_mock = mocker.patch.object(AesTransport, "send", return_value=mock_response)
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), batch_size=batch_size
    )
    protocol = SmartProtocol(transport=AesTransport(config=config))

    await protocol.query(requests, retry_count=0)
    expected_count = int(request_size / batch_size) + (request_size % batch_size > 0)
    assert send_mock.call_count == expected_count


async def test_responsedata_unwrapping(dummy_protocol, mocker):
    """Test that responseData gets unwrapped correctly."""
    mock_response = {"error_code": 0, "result": {"responseData": {"error_code": 0}}}

    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    res = await dummy_protocol.query(DUMMY_QUERY)
    assert res == {"foobar": None}


async def test_responsedata_unwrapping_with_payload(dummy_protocol, mocker):
    mock_response = {
        "error_code": 0,
        "result": {"responseData": {"error_code": 0, "result": {"bar": "bar"}}},
    }
    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    res = await dummy_protocol.query(DUMMY_QUERY)
    assert res == {"foobar": {"bar": "bar"}}


async def test_responsedata_error(dummy_protocol, mocker):
    """Test that errors inside the responseData payload cause an exception."""
    mock_response = {"error_code": 0, "result": {"responseData": {"error_code": -1001}}}

    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    with pytest.raises(SmartDeviceException):
        await dummy_protocol.query(DUMMY_QUERY)


async def test_responsedata_unwrapping_multiplerequest(dummy_protocol, mocker):
    """Test that unwrapping multiplerequest works correctly."""
    mock_response = {
        "error_code": 0,
        "result": {
            "responseData": {
                "result": {
                    "responses": [
                        {
                            "error_code": 0,
                            "method": "get_device_info",
                            "result": {"foo": "bar"},
                        },
                        {
                            "error_code": 0,
                            "method": "second_command",
                            "result": {"bar": "foo"},
                        },
                    ]
                }
            }
        },
    }

    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    resp = await dummy_protocol.query(DUMMY_QUERY)
    assert resp == {"get_device_info": {"foo": "bar"}, "second_command": {"bar": "foo"}}


async def test_responsedata_multiplerequest_error(dummy_protocol, mocker):
    """Test that errors inside multipleRequest response of responseData raise an exception."""
    mock_response = {
        "error_code": 0,
        "result": {
            "responseData": {
                "result": {
                    "responses": [
                        {
                            "error_code": 0,
                            "method": "get_device_info",
                            "result": {"foo": "bar"},
                        },
                        {"error_code": -1001, "method": "invalid_command"},
                    ]
                }
            }
        },
    }

    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    with pytest.raises(SmartDeviceException):
        await dummy_protocol.query(DUMMY_QUERY)
