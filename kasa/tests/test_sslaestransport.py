from __future__ import annotations

import logging
import secrets
from contextlib import nullcontext as does_not_raise
from json import dumps as json_dumps
from json import loads as json_loads
from typing import Any

import aiohttp
import pytest
from yarl import URL

from kasa.protocol import DEFAULT_CREDENTIALS, get_default_credentials

from ..aestransport import AesEncyptionSession
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    AuthenticationError,
    KasaException,
    SmartErrorCode,
)
from ..experimental.sslaestransport import SslAesTransport, TransportState, _sha256_hash
from ..httpclient import HttpClient

MOCK_ADMIN_USER = get_default_credentials(DEFAULT_CREDENTIALS["TAPOCAMERA"]).username
MOCK_PWD = "correct_pwd"  # noqa: S105
MOCK_USER = "mock@example.com"
MOCK_STOCK = "abcdefghijklmnopqrstuvwxyz1234)("


@pytest.mark.parametrize(
    (
        "status_code",
        "username",
        "password",
        "wants_default_user",
        "digest_password_fail",
        "expectation",
    ),
    [
        pytest.param(
            200, MOCK_USER, MOCK_PWD, False, False, does_not_raise(), id="success"
        ),
        pytest.param(
            200,
            MOCK_USER,
            MOCK_PWD,
            True,
            False,
            does_not_raise(),
            id="success-default",
        ),
        pytest.param(
            400,
            MOCK_USER,
            MOCK_PWD,
            False,
            False,
            pytest.raises(KasaException),
            id="400 error",
        ),
        pytest.param(
            200,
            "foobar",
            MOCK_PWD,
            False,
            False,
            pytest.raises(AuthenticationError),
            id="bad-username",
        ),
        pytest.param(
            200,
            MOCK_USER,
            "barfoo",
            False,
            False,
            pytest.raises(AuthenticationError),
            id="bad-password",
        ),
        pytest.param(
            200,
            MOCK_USER,
            MOCK_PWD,
            False,
            True,
            pytest.raises(AuthenticationError),
            id="bad-password-digest",
        ),
    ],
)
async def test_handshake(
    mocker,
    status_code,
    username,
    password,
    wants_default_user,
    digest_password_fail,
    expectation,
):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        status_code=status_code,
        want_default_username=wants_default_user,
        digest_password_fail=digest_password_fail,
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslAesTransport(
        config=DeviceConfig(host, credentials=Credentials(username, password))
    )

    assert transport._encryption_session is None
    assert transport._state is TransportState.HANDSHAKE_REQUIRED
    with expectation:
        await transport.perform_handshake()
        assert transport._encryption_session is not None
        assert transport._state is TransportState.ESTABLISHED


@pytest.mark.parametrize(
    ("wants_default_user"),
    [pytest.param(False, id="username"), pytest.param(True, id="default")],
)
async def test_credentials_hash(mocker, wants_default_user):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(
        host, want_default_username=wants_default_user
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )
    creds = Credentials(MOCK_USER, MOCK_PWD)
    creds_hash = SslAesTransport._create_b64_credentials(creds)

    # Test with credentials input
    transport = SslAesTransport(config=DeviceConfig(host, credentials=creds))
    assert transport.credentials_hash == creds_hash
    await transport.perform_handshake()
    assert transport.credentials_hash == creds_hash

    # Test with credentials_hash input
    transport = SslAesTransport(config=DeviceConfig(host, credentials_hash=creds_hash))
    mock_ssl_aes_device.handshake1_complete = False
    assert transport.credentials_hash == creds_hash
    await transport.perform_handshake()
    assert transport.credentials_hash == creds_hash


async def test_send(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(host, want_default_username=False)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslAesTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )
    request = {
        "method": "getDeviceInfo",
        "params": None,
    }

    res = await transport.send(json_dumps(request))
    assert "result" in res


async def test_unencrypted_response(mocker, caplog):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(host, do_not_encrypt_response=True)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslAesTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )

    request = {
        "method": "getDeviceInfo",
        "params": None,
    }
    caplog.set_level(logging.DEBUG)
    res = await transport.send(json_dumps(request))
    assert "result" in res
    assert (
        "Received unencrypted response over secure passthrough from 127.0.0.1"
        in caplog.text
    )


async def test_port_override():
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    port_override = 12345
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=port_override
    )
    transport = SslAesTransport(config=config)

    assert str(transport._app_url) == f"https://127.0.0.1:{port_override}"


class MockSslAesDevice:
    BAD_USER_RESP = {
        "error_code": SmartErrorCode.SESSION_EXPIRED.value,
        "result": {
            "data": {
                "code": -60502,
            }
        },
    }

    BAD_PWD_RESP = {
        "error_code": SmartErrorCode.INVALID_NONCE.value,
        "result": {
            "data": {
                "code": SmartErrorCode.SESSION_EXPIRED.value,
                "encrypt_type": ["3"],
                "key": "Someb64keyWithUnknownPurpose",
                "nonce": "1234567890ABCDEF",  # Whatever the original nonce was
                "device_confirm": "",
            }
        },
    }

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
        want_default_username: bool = False,
        do_not_encrypt_response=False,
        send_response=None,
        sequential_request_delay=0,
        send_error_code=0,
        secure_passthrough_error_code=0,
        digest_password_fail=False,
    ):
        self.host = host
        self.http_client = HttpClient(DeviceConfig(self.host))
        self.encryption_session: AesEncyptionSession | None = None
        self.server_nonce = secrets.token_bytes(8).hex().upper()
        self.handshake1_complete = False

        # test behaviour attributes
        self.status_code = status_code
        self.send_error_code = send_error_code
        self.secure_passthrough_error_code = secure_passthrough_error_code
        self.do_not_encrypt_response = do_not_encrypt_response
        self.want_default_username = want_default_username
        self.digest_password_fail = digest_password_fail

    async def post(self, url: URL, params=None, json=None, data=None, *_, **__):
        if data:
            json = json_loads(data)
        res = await self._post(url, json)
        return res

    async def _post(self, url: URL, json: dict[str, Any]):
        method = json["method"]

        if method == "login" and not self.handshake1_complete:
            return await self._return_handshake1_response(url, json)

        if method == "login" and self.handshake1_complete:
            return await self._return_handshake2_response(url, json)
        elif method == "securePassthrough":
            assert url == URL(f"https://{self.host}/stok={MOCK_STOCK}/ds")
            return await self._return_secure_passthrough_response(url, json)
        else:
            assert url == URL(f"https://{self.host}/stok={MOCK_STOCK}/ds")
            return await self._return_send_response(url, json)

    async def _return_handshake1_response(self, url: URL, request: dict[str, Any]):
        request_nonce = request["params"].get("cnonce")
        request_username = request["params"].get("username")

        if (self.want_default_username and request_username != MOCK_ADMIN_USER) or (
            not self.want_default_username and request_username != MOCK_USER
        ):
            return self._mock_response(self.status_code, self.BAD_USER_RESP)

        device_confirm = SslAesTransport.generate_confirm_hash(
            request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        self.handshake1_complete = True
        resp = {
            "error_code": SmartErrorCode.INVALID_NONCE.value,
            "result": {
                "data": {
                    "code": SmartErrorCode.INVALID_NONCE.value,
                    "encrypt_type": ["3"],
                    "key": "Someb64keyWithUnknownPurpose",
                    "nonce": self.server_nonce,
                    "device_confirm": device_confirm,
                }
            },
        }
        return self._mock_response(self.status_code, resp)

    async def _return_handshake2_response(self, url: URL, request: dict[str, Any]):
        request_nonce = request["params"].get("cnonce")
        request_username = request["params"].get("username")
        if (self.want_default_username and request_username != MOCK_ADMIN_USER) or (
            not self.want_default_username and request_username != MOCK_USER
        ):
            return self._mock_response(self.status_code, self.BAD_USER_RESP)

        request_password = request["params"].get("digest_passwd")
        expected_pwd = SslAesTransport.generate_digest_password(
            request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        if request_password != expected_pwd or self.digest_password_fail:
            return self._mock_response(self.status_code, self.BAD_PWD_RESP)

        lsk = SslAesTransport.generate_encryption_token(
            "lsk", request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        ivb = SslAesTransport.generate_encryption_token(
            "ivb", request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        self.encryption_session = AesEncyptionSession(lsk, ivb)
        resp = {
            "error_code": 0,
            "result": {"stok": MOCK_STOCK, "user_group": "root", "start_seq": 100},
        }
        return self._mock_response(self.status_code, resp)

    async def _return_secure_passthrough_response(self, url: URL, json: dict[str, Any]):
        encrypted_request = json["params"]["request"]
        assert self.encryption_session
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
            "error_code": self.secure_passthrough_error_code,
        }
        return self._mock_response(self.status_code, result)

    async def _return_send_response(self, url: URL, json: dict[str, Any]):
        result = {"result": {"method": None}, "error_code": self.send_error_code}
        return self._mock_response(self.status_code, result)
