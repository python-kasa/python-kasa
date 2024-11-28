from __future__ import annotations

import logging
from base64 import b64encode
from contextlib import nullcontext as does_not_raise
from json import dumps as json_dumps
from json import loads as json_loads
from typing import Any

import aiohttp
import pytest
from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    AuthenticationError,
    KasaException,
    SmartErrorCode,
)
from kasa.httpclient import HttpClient
from kasa.transports import SslTransport
from kasa.transports.ssltransport import TransportState, _md5

# Transport tests are not designed for real devices
pytestmark = [pytest.mark.requires_dummy]

MOCK_PWD = "correct_pwd"  # noqa: S105
MOCK_USER = "mock@example.com"
MOCK_BAD_USER_OR_PWD = "foobar"  # noqa: S105
MOCK_TOKEN = "abcdefghijklmnopqrstuvwxyz1234)("  # noqa: S105
MOCK_ERROR_CODE = -10_000

DEFAULT_CREDS = get_default_credentials(DEFAULT_CREDENTIALS["TAPO"])


def _get_password_hash(pw):
    return _md5(pw.encode()).upper()


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
        pytest.param(200, 0, MOCK_USER, MOCK_PWD, does_not_raise(), id="success"),
        pytest.param(
            400,
            MOCK_ERROR_CODE,
            MOCK_USER,
            MOCK_PWD,
            pytest.raises(KasaException),
            id="400 error",
        ),
        pytest.param(
            200,
            MOCK_ERROR_CODE,
            MOCK_BAD_USER_OR_PWD,
            MOCK_PWD,
            pytest.raises(AuthenticationError),
            id="bad-username",
        ),
        pytest.param(
            200,
            MOCK_ERROR_CODE,
            MOCK_USER,
            MOCK_BAD_USER_OR_PWD,
            pytest.raises(AuthenticationError),
            id="bad-password",
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


async def test_credentials_hash(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(host)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )
    creds = Credentials(MOCK_USER, MOCK_PWD)

    data = {"password": _get_password_hash(MOCK_PWD), "username": MOCK_USER}

    creds_hash = b64encode(json_dumps(data).encode()).decode()

    # Test with credentials input
    transport = SslTransport(config=DeviceConfig(host, credentials=creds))
    assert transport.credentials_hash == creds_hash

    # Test with credentials_hash input
    transport = SslTransport(config=DeviceConfig(host, credentials_hash=creds_hash))
    assert transport.credentials_hash == creds_hash


async def test_send(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslDevice(host)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )
    request = {
        "method": "get_device_info",
        "params": None,
    }

    res = await transport.send(json_dumps(request))
    assert "result" in res


async def test_port_override():
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    port_override = 12345
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=port_override
    )
    transport = SslTransport(config=config)

    assert str(transport._app_url) == f"https://127.0.0.1:{port_override}/app"


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
        send_error_code=0,
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

        if (
            request_username == MOCK_BAD_USER_OR_PWD
            or request_username == DEFAULT_CREDS.username
        ) or (
            request_password == _get_password_hash(MOCK_BAD_USER_OR_PWD)
            or request_password == _get_password_hash(DEFAULT_CREDS.password)
        ):
            resp = {
                "error_code": SmartErrorCode.LOGIN_ERROR.value,
                "result": {"unknown": "payload"},
            }
            _LOGGER.debug("Returning login error with status %s", self.status_code)
            return self._mock_response(self.status_code, resp)

        resp = {
            "error_code": SmartErrorCode.SUCCESS.value,
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
            "error_code": self.send_error_code,
        }
        return self._mock_response(self.status_code, result)
