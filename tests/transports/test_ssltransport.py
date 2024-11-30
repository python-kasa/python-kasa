from __future__ import annotations

import logging
from base64 import b64encode
from contextlib import nullcontext as does_not_raise
from typing import Any

import aiohttp
import pytest
from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.transports import SslTransport
from kasa.transports.ssltransport import TransportState, _md5_hash

# Transport tests are not designed for real devices
pytestmark = [pytest.mark.requires_dummy]

MOCK_PWD = "correct_pwd"  # noqa: S105
MOCK_USER = "mock@example.com"
MOCK_BAD_USER_OR_PWD = "foobar"  # noqa: S105
MOCK_TOKEN = "abcdefghijklmnopqrstuvwxyz1234)("  # noqa: S105

DEFAULT_CREDS = get_default_credentials(DEFAULT_CREDENTIALS["TAPO"])


_LOGGER = logging.getLogger(__name__)


@pytest.mark.parametrize(
    (
        "status_code",
        "error_code",
        "username",
        "password",
        "expectation",
    ),
    [
        pytest.param(
            200,
            SmartErrorCode.SUCCESS,
            MOCK_USER,
            MOCK_PWD,
            does_not_raise(),
            id="success",
        ),
        pytest.param(
            200,
            SmartErrorCode.UNSPECIFIC_ERROR,
            MOCK_USER,
            MOCK_PWD,
            pytest.raises(_RetryableError),
            id="test retry",
        ),
        pytest.param(
            200,
            SmartErrorCode.DEVICE_BLOCKED,
            MOCK_USER,
            MOCK_PWD,
            pytest.raises(DeviceError),
            id="test regular error",
        ),
        pytest.param(
            400,
            SmartErrorCode.INTERNAL_UNKNOWN_ERROR,
            MOCK_USER,
            MOCK_PWD,
            pytest.raises(KasaException),
            id="400 error",
        ),
        pytest.param(
            200,
            SmartErrorCode.LOGIN_ERROR,
            MOCK_BAD_USER_OR_PWD,
            MOCK_PWD,
            pytest.raises(AuthenticationError),
            id="bad-username",
        ),
        pytest.param(
            200,
            [SmartErrorCode.LOGIN_ERROR, SmartErrorCode.SUCCESS],
            MOCK_BAD_USER_OR_PWD,
            "",
            does_not_raise(),
            id="working-fallback",
        ),
        pytest.param(
            200,
            [SmartErrorCode.LOGIN_ERROR, SmartErrorCode.LOGIN_ERROR],
            MOCK_BAD_USER_OR_PWD,
            "",
            pytest.raises(AuthenticationError),
            id="fallback-fail",
        ),
        pytest.param(
            200,
            SmartErrorCode.LOGIN_ERROR,
            MOCK_USER,
            MOCK_BAD_USER_OR_PWD,
            pytest.raises(AuthenticationError),
            id="bad-password",
        ),
        pytest.param(
            200,
            SmartErrorCode.TRANSPORT_UNKNOWN_CREDENTIALS_ERROR,
            MOCK_USER,
            MOCK_PWD,
            pytest.raises(AuthenticationError),
            id="auth-error != login_error",
        ),
    ],
)
async def test_login(
    mocker,
    status_code,
    error_code,
    username,
    password,
    expectation,
):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(
        host,
        status_code=status_code,
        send_error_code=error_code,
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslTransport(
        config=DeviceConfig(host, credentials=Credentials(username, password))
    )

    assert transport._state is TransportState.LOGIN_REQUIRED
    with expectation:
        await transport.perform_login()
        assert transport._state is TransportState.ESTABLISHED

    await transport.close()


async def test_credentials_hash(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(host)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )
    creds = Credentials(MOCK_USER, MOCK_PWD)

    data = {"password": _md5_hash(MOCK_PWD.encode()), "username": MOCK_USER}

    creds_hash = b64encode(json_dumps(data).encode()).decode()

    # Test with credentials input
    transport = SslTransport(config=DeviceConfig(host, credentials=creds))
    assert transport.credentials_hash == creds_hash

    # Test with credentials_hash input
    transport = SslTransport(config=DeviceConfig(host, credentials_hash=creds_hash))
    assert transport.credentials_hash == creds_hash

    await transport.close()


async def test_send(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(host, send_error_code=SmartErrorCode.SUCCESS)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )
    try_login_spy = mocker.spy(transport, "try_login")
    request = {
        "method": "get_device_info",
        "params": None,
    }
    assert transport._state is TransportState.LOGIN_REQUIRED

    res = await transport.send(json_dumps(request))
    assert "result" in res
    try_login_spy.assert_called_once()
    assert transport._state is TransportState.ESTABLISHED

    # Second request does not
    res = await transport.send(json_dumps(request))
    try_login_spy.assert_called_once()

    await transport.close()


async def test_no_credentials(mocker):
    """Test transport without credentials."""
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(
        host, send_error_code=SmartErrorCode.LOGIN_ERROR
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslTransport(config=DeviceConfig(host))
    try_login_spy = mocker.spy(transport, "try_login")

    with pytest.raises(AuthenticationError):
        await transport.send('{"method": "dummy"}')

    # We get called twice
    assert try_login_spy.call_count == 2

    await transport.close()


async def test_reset(mocker):
    """Test that transport state adjusts correctly for reset."""
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(host, send_error_code=SmartErrorCode.SUCCESS)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )

    assert transport._state is TransportState.LOGIN_REQUIRED
    assert str(transport._app_url) == "https://127.0.0.1:4433/app"

    await transport.perform_login()
    assert transport._state is TransportState.ESTABLISHED
    assert str(transport._app_url).startswith("https://127.0.0.1:4433/app?token=")

    await transport.close()
    assert transport._state is TransportState.LOGIN_REQUIRED
    assert str(transport._app_url) == "https://127.0.0.1:4433/app"


async def test_port_override():
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    port_override = 12345
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=port_override
    )
    transport = SslTransport(config=config)

    assert str(transport._app_url) == f"https://127.0.0.1:{port_override}/app"

    await transport.close()


class MockSslDevice:
    """Based on MockAesSslDevice."""

    class _mock_response:
        def __init__(self, status, request: dict):
            self.status = status
            self._json = request

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_t, exc_v, exc_tb):
            pass

        async def read(self):
            if isinstance(self._json, dict):
                return json_dumps(self._json).encode()
            return self._json

    def __init__(
        self,
        host,
        *,
        status_code=200,
        send_error_code=SmartErrorCode.INTERNAL_UNKNOWN_ERROR,
    ):
        self.host = host
        self.http_client = HttpClient(DeviceConfig(self.host))

        self._state = TransportState.LOGIN_REQUIRED

        # test behaviour attributes
        self.status_code = status_code
        self.send_error_code = send_error_code

    async def post(self, url: URL, params=None, json=None, data=None, *_, **__):
        if data:
            json = json_loads(data)
        _LOGGER.warning("Request %s: %s", url, json)
        res = self._post(url, json)
        _LOGGER.warning("Response %s, data: %s", res, await res.read())
        return res

    def _post(self, url: URL, json: dict[str, Any]):
        method = json["method"]

        if method == "login":
            if self._state is TransportState.LOGIN_REQUIRED:
                assert json.get("token") is None
                assert url == URL(f"https://{self.host}:4433/app")
                return self._return_login_response(url, json)
            else:
                _LOGGER.warning("Received login although already logged in")
                pytest.fail("non-handled re-login logic")

        assert url == URL(f"https://{self.host}:4433/app?token={MOCK_TOKEN}")
        return self._return_send_response(url, json)

    def _return_login_response(self, url: URL, request: dict[str, Any]):
        request_username = request["params"].get("username")
        request_password = request["params"].get("password")

        _LOGGER.warning("error codes: %s", self.send_error_code)
        # Handle multiple error codes
        if isinstance(self.send_error_code, list):
            error_code = self.send_error_code.pop(0)
        else:
            error_code = self.send_error_code

        _LOGGER.warning("using error code %s", error_code)

        def _return_login_error():
            resp = {
                "error_code": error_code.value,
                "result": {"unknown": "payload"},
            }

            _LOGGER.debug("Returning login error with status %s", self.status_code)
            return self._mock_response(self.status_code, resp)

        if error_code is not SmartErrorCode.SUCCESS:
            # Bad username
            if request_username == MOCK_BAD_USER_OR_PWD:
                return _return_login_error()

            # Bad password
            if request_password == _md5_hash(MOCK_BAD_USER_OR_PWD.encode()):
                return _return_login_error()

            # Empty password
            if request_password == _md5_hash(b""):
                return _return_login_error()

        self._state = TransportState.ESTABLISHED
        resp = {
            "error_code": error_code.value,
            "result": {
                "token": MOCK_TOKEN,
            },
        }
        _LOGGER.debug("Returning login success with status %s", self.status_code)
        return self._mock_response(self.status_code, resp)

    def _return_send_response(self, url: URL, json: dict[str, Any]):
        method = json["method"]
        result = {
            "result": {method: {"dummy": "response"}},
            "error_code": self.send_error_code.value,
        }
        return self._mock_response(self.status_code, result)
