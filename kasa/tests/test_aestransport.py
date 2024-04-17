from __future__ import annotations

import base64
import json
import logging
import random
import string
import time
from contextlib import nullcontext as does_not_raise
from json import dumps as json_dumps
from json import loads as json_loads
from typing import Any

import aiohttp
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from yarl import URL

from ..aestransport import AesEncyptionSession, AesTransport, TransportState
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    AuthenticationError,
    KasaException,
    SmartErrorCode,
)
from ..httpclient import HttpClient

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}

key = b"8\x89\x02\xfa\xf5Xs\x1c\xa1 H\x9a\x82\xc7\xd9\t"
iv = b"9=\xf8\x1bS\xcd0\xb5\x89i\xba\xfd^9\x9f\xfa"
KEY_IV = key + iv


def test_encrypt():
    encryption_session = AesEncyptionSession(KEY_IV[:16], KEY_IV[16:])

    d = json.dumps({"foo": 1, "bar": 2})
    encrypted = encryption_session.encrypt(d.encode())
    assert d == encryption_session.decrypt(encrypted)

    # test encrypt unicode
    d = "{'snowman': '\u2603'}"
    encrypted = encryption_session.encrypt(d.encode())
    assert d == encryption_session.decrypt(encrypted)


status_parameters = pytest.mark.parametrize(
    "status_code, error_code, inner_error_code, expectation",
    [
        (200, 0, 0, does_not_raise()),
        (400, 0, 0, pytest.raises(KasaException)),
        (200, -1, 0, pytest.raises(KasaException)),
    ],
    ids=("success", "status_code", "error_code"),
)


@status_parameters
async def test_handshake(
    mocker, status_code, error_code, inner_error_code, expectation
):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, status_code, error_code, inner_error_code)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )

    assert transport._encryption_session is None
    assert transport._state is TransportState.HANDSHAKE_REQUIRED
    with expectation:
        await transport.perform_handshake()
        assert transport._encryption_session is not None
        assert transport._state is TransportState.LOGIN_REQUIRED


@status_parameters
async def test_login(mocker, status_code, error_code, inner_error_code, expectation):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, status_code, error_code, inner_error_code)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )
    transport._state = TransportState.LOGIN_REQUIRED
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session

    assert transport._token_url is None
    with expectation:
        await transport.perform_login()
        assert mock_aes_device.token in str(transport._token_url)


@pytest.mark.parametrize(
    "inner_error_codes, expectation, call_count",
    [
        ([SmartErrorCode.LOGIN_ERROR, 0, 0, 0], does_not_raise(), 4),
        (
            [SmartErrorCode.LOGIN_ERROR, SmartErrorCode.LOGIN_ERROR],
            pytest.raises(AuthenticationError),
            3,
        ),
        (
            [SmartErrorCode.LOGIN_FAILED_ERROR],
            pytest.raises(AuthenticationError),
            1,
        ),
        (
            [SmartErrorCode.LOGIN_ERROR, SmartErrorCode.SESSION_TIMEOUT_ERROR],
            pytest.raises(KasaException),
            3,
        ),
    ],
    ids=(
        "LOGIN_ERROR-success",
        "LOGIN_ERROR-LOGIN_ERROR",
        "LOGIN_FAILED_ERROR",
        "LOGIN_ERROR-SESSION_TIMEOUT_ERROR",
    ),
)
async def test_login_errors(mocker, inner_error_codes, expectation, call_count):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, 200, 0, inner_error_codes)
    post_mock = mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_aes_device.post
    )

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )
    transport._state = TransportState.LOGIN_REQUIRED
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session
    mocker.patch.object(transport, "BACKOFF_SECONDS_AFTER_LOGIN_ERROR", 0)

    assert transport._token_url is None

    request = {
        "method": "get_device_info",
        "params": None,
        "request_time_milis": round(time.time() * 1000),
        "requestID": 1,
        "terminal_uuid": "foobar",
    }

    with expectation:
        await transport.send(json_dumps(request))
        assert mock_aes_device.token in str(transport._token_url)
        assert post_mock.call_count == call_count  # Login, Handshake, Login
        await transport.close()


@status_parameters
async def test_send(mocker, status_code, error_code, inner_error_code, expectation):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, status_code, error_code, inner_error_code)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )
    transport._handshake_done = True
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session
    transport._token_url = transport._app_url.with_query(
        f"token={mock_aes_device.token}"
    )

    request = {
        "method": "get_device_info",
        "params": None,
        "request_time_milis": round(time.time() * 1000),
        "requestID": 1,
        "terminal_uuid": "foobar",
    }
    with expectation:
        res = await transport.send(json_dumps(request))
        assert "result" in res


async def test_unencrypted_response(mocker, caplog):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, 200, 0, 0, do_not_encrypt_response=True)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )
    transport._state = TransportState.ESTABLISHED
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session
    transport._token_url = transport._app_url.with_query(
        f"token={mock_aes_device.token}"
    )

    request = {
        "method": "get_device_info",
        "params": None,
        "request_time_milis": round(time.time() * 1000),
        "requestID": 1,
        "terminal_uuid": "foobar",
    }
    caplog.set_level(logging.DEBUG)
    res = await transport.send(json_dumps(request))
    assert "result" in res
    assert (
        "Received unencrypted response over secure passthrough from 127.0.0.1"
        in caplog.text
    )


async def test_unencrypted_response_invalid_json(mocker, caplog):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(
        host, 200, 0, 0, do_not_encrypt_response=True, send_response=b"Foobar"
    )
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    transport = AesTransport(
        config=DeviceConfig(host, credentials=Credentials("foo", "bar"))
    )
    transport._state = TransportState.ESTABLISHED
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session
    transport._token_url = transport._app_url.with_query(
        f"token={mock_aes_device.token}"
    )

    request = {
        "method": "get_device_info",
        "params": None,
        "request_time_milis": round(time.time() * 1000),
        "requestID": 1,
        "terminal_uuid": "foobar",
    }
    caplog.set_level(logging.DEBUG)
    msg = f"Unable to decrypt response from {host}, error: Incorrect padding, response: Foobar"
    with pytest.raises(KasaException, match=msg):
        await transport.send(json_dumps(request))


ERRORS = [e for e in SmartErrorCode if e != 0]


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_passthrough_errors(mocker, error_code):
    host = "127.0.0.1"
    mock_aes_device = MockAesDevice(host, 200, error_code, 0)
    mocker.patch.object(aiohttp.ClientSession, "post", side_effect=mock_aes_device.post)

    config = DeviceConfig(host, credentials=Credentials("foo", "bar"))
    transport = AesTransport(config=config)
    transport._handshake_done = True
    transport._session_expire_at = time.time() + 86400
    transport._encryption_session = mock_aes_device.encryption_session
    transport._token_url = transport._app_url.with_query(
        f"token={mock_aes_device.token}"
    )

    request = {
        "method": "get_device_info",
        "params": None,
        "request_time_milis": round(time.time() * 1000),
        "requestID": 1,
        "terminal_uuid": "foobar",
    }
    with pytest.raises(KasaException):
        await transport.send(json_dumps(request))


async def test_port_override():
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=12345
    )
    transport = AesTransport(config=config)

    assert str(transport._app_url) == "http://127.0.0.1:12345/app"


class MockAesDevice:
    class _mock_response:
        def __init__(self, status, json: dict):
            self.status = status
            self._json = json

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
            if isinstance(self._json, dict):
                return json_dumps(self._json).encode()
            return self._json

    encryption_session = AesEncyptionSession(KEY_IV[:16], KEY_IV[16:])

    def __init__(
        self,
        host,
        status_code=200,
        error_code=0,
        inner_error_code=0,
        *,
        do_not_encrypt_response=False,
        send_response=None,
    ):
        self.host = host
        self.status_code = status_code
        self.error_code = error_code
        self._inner_error_code = inner_error_code
        self.do_not_encrypt_response = do_not_encrypt_response
        self.send_response = send_response
        self.http_client = HttpClient(DeviceConfig(self.host))
        self.inner_call_count = 0
        self.token = "".join(random.choices(string.ascii_uppercase, k=32))  # noqa: S311

    @property
    def inner_error_code(self):
        if isinstance(self._inner_error_code, list):
            return self._inner_error_code[self.inner_call_count]
        else:
            return self._inner_error_code

    async def post(self, url: URL, params=None, json=None, data=None, *_, **__):
        if data:
            async for item in data:
                json = json_loads(item.decode())
        return await self._post(url, json)

    async def _post(self, url: URL, json: dict[str, Any]):
        if json["method"] == "handshake":
            return await self._return_handshake_response(url, json)
        elif json["method"] == "securePassthrough":
            return await self._return_secure_passthrough_response(url, json)
        elif json["method"] == "login_device":
            return await self._return_login_response(url, json)
        else:
            assert str(url) == f"http://{self.host}:80/app?token={self.token}"
            return await self._return_send_response(url, json)

    async def _return_handshake_response(self, url: URL, json: dict[str, Any]):
        start = len("-----BEGIN PUBLIC KEY-----\n")
        end = len("\n-----END PUBLIC KEY-----\n")
        client_pub_key = json["params"]["key"][start:-end]

        client_pub_key_data = base64.b64decode(client_pub_key.encode())
        client_pub_key = serialization.load_der_public_key(client_pub_key_data, None)
        encrypted_key = client_pub_key.encrypt(KEY_IV, asymmetric_padding.PKCS1v15())
        key_64 = base64.b64encode(encrypted_key).decode()
        return self._mock_response(
            self.status_code, {"result": {"key": key_64}, "error_code": self.error_code}
        )

    async def _return_secure_passthrough_response(self, url: URL, json: dict[str, Any]):
        encrypted_request = json["params"]["request"]
        decrypted_request = self.encryption_session.decrypt(encrypted_request.encode())
        decrypted_request_dict = json_loads(decrypted_request)
        decrypted_response = await self._post(url, decrypted_request_dict)
        async with decrypted_response:
            decrypted_response_data = await decrypted_response.read()
        encrypted_response = self.encryption_session.encrypt(decrypted_response_data)
        response = (
            decrypted_response_data
            if self.do_not_encrypt_response
            else encrypted_response
        )
        result = {
            "result": {"response": response.decode()},
            "error_code": self.error_code,
        }
        return self._mock_response(self.status_code, result)

    async def _return_login_response(self, url: URL, json: dict[str, Any]):
        if "token=" in str(url):
            raise Exception("token should not be in url for a login request")
        self.token = "".join(random.choices(string.ascii_uppercase, k=32))  # noqa: S311
        result = {"result": {"token": self.token}, "error_code": self.inner_error_code}
        self.inner_call_count += 1
        return self._mock_response(self.status_code, result)

    async def _return_send_response(self, url: URL, json: dict[str, Any]):
        result = {"result": {"method": None}, "error_code": self.inner_error_code}
        response = self.send_response if self.send_response else result
        self.inner_call_count += 1
        return self._mock_response(self.status_code, response)
