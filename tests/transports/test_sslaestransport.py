from __future__ import annotations

import base64
import logging
import secrets
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
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.transports.aestransport import AesEncyptionSession
from kasa.transports.sslaestransport import (
    SslAesTransport,
    TransportState,
    _md5_hash,
    _sha256_hash,
)

# Transport tests are not designed for real devices
# SslAesTransport use a socket to get it's own ip address
pytestmark = [pytest.mark.requires_dummy, pytest.mark.enable_socket]

MOCK_ADMIN_USER = get_default_credentials(DEFAULT_CREDENTIALS["TAPOCAMERA"]).username
MOCK_PWD = "correct_pwd"  # noqa: S105
MOCK_USER = "mock@example.com"
MOCK_STOCK = "abcdefghijklmnopqrstuvwxyz1234)("
MOCK_UNENCRYPTED_PASSTHROUGH_STOK = "32charLowerCaseHexStok"


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


@pytest.mark.xdist_group(name="caplog")
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


@pytest.mark.parametrize(("want_default"), [True, False])
@pytest.mark.xdist_group(name="caplog")
async def test_unencrypted_passthrough(mocker, caplog, want_default):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(
        host, unencrypted_passthrough=True, want_default_username=want_default
    )
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
        f"Succesfully logged in to {host} with less secure passthrough" in caplog.text
    )


@pytest.mark.parametrize(("want_default"), [True, False])
@pytest.mark.xdist_group(name="caplog")
async def test_unencrypted_passthrough_errors(mocker, caplog, want_default):
    host = "127.0.0.1"
    request = {
        "method": "getDeviceInfo",
        "params": None,
    }
    transport = SslAesTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )
    caplog.set_level(logging.DEBUG)

    # Test bad password
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        unencrypted_passthrough=True,
        want_default_username=want_default,
        digest_password_fail=True,
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    msg = f"Unable to log in to {host} with less secure login"
    with pytest.raises(AuthenticationError):
        await transport.send(json_dumps(request))

    assert msg in caplog.text

    # Test bad status code in handshake
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        unencrypted_passthrough=True,
        want_default_username=want_default,
        status_code=401,
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    msg = f"{host} responded with an unexpected status code 401 to handshake1"
    with pytest.raises(KasaException, match=msg):
        await transport.send(json_dumps(request))

    # Test bad status code in login
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        unencrypted_passthrough=True,
        want_default_username=want_default,
        status_code_list=[200, 401],
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    msg = f"{host} responded with an unexpected status code 401 to login"
    with pytest.raises(KasaException, match=msg):
        await transport.send(json_dumps(request))

    # Test bad status code in send
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        unencrypted_passthrough=True,
        want_default_username=want_default,
        status_code_list=[200, 200, 401],
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    msg = f"{host} responded with an unexpected status code 401 to unencrypted send"
    with pytest.raises(KasaException, match=msg):
        await transport.send(json_dumps(request))

    # Test error code in send response
    mock_ssl_aes_device = MockSslAesDevice(
        host,
        unencrypted_passthrough=True,
        want_default_username=want_default,
        send_error_code=SmartErrorCode.BAD_USERNAME.value,
    )
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    msg = f"Error sending message: {host}:"
    with pytest.raises(KasaException, match=msg):
        await transport.send(json_dumps(request))


async def test_device_blocked_response(mocker):
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(host, device_blocked=True)
    mocker.patch.object(
        aiohttp.ClientSession, "post", side_effect=mock_ssl_aes_device.post
    )

    transport = SslAesTransport(
        config=DeviceConfig(host, credentials=Credentials(MOCK_USER, MOCK_PWD))
    )
    msg = "Device blocked for 1685 seconds"

    with pytest.raises(DeviceError, match=msg):
        await transport.perform_handshake()


@pytest.mark.parametrize(
    ("response", "expected_msg"),
    [
        pytest.param(
            {"error_code": -1, "msg": "Check tapo tag failed"},
            '{"error_code": -1, "msg": "Check tapo tag failed"}',
            id="can-decrypt",
        ),
        pytest.param(
            b"12345678",
            str({"result": {"response": "12345678"}, "error_code": 0}),
            id="cannot-decrypt",
        ),
    ],
)
async def test_device_500_error(mocker, response, expected_msg):
    """Test 500 error raises retryable exception."""
    host = "127.0.0.1"
    mock_ssl_aes_device = MockSslAesDevice(host)
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

    await transport.perform_handshake()

    mock_ssl_aes_device.put_next_response(response)
    mock_ssl_aes_device.status_code = 500

    msg = f"Device 127.0.0.1 replied with status 500 after handshake, response: {expected_msg}"
    with pytest.raises(_RetryableError, match=msg):
        await transport.send(json_dumps(request))


async def test_port_override():
    """Test that port override sets the app_url."""
    host = "127.0.0.1"
    port_override = 12345
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), port_override=port_override
    )
    transport = SslAesTransport(config=config)

    assert str(transport._app_url) == f"https://127.0.0.1:{port_override}"


async def test_login_version_get_credentials():
    """Test that login_version is passed to get_default_credentials."""
    creds = get_default_credentials(DEFAULT_CREDENTIALS["TAPOCAMERA"], login_version=3)
    assert creds.username == "admin"
    password_b64 = base64.b64encode(creds.password.encode()).decode()
    assert password_b64 == "VFBMMDc1NTI2NDYwNjAz"  # noqa: S105
    creds = get_default_credentials(DEFAULT_CREDENTIALS["TAPOCAMERA"], login_version=2)
    assert creds.username == "admin"
    password_b64 = base64.b64encode(creds.password.encode()).decode()
    assert password_b64 == "YWRtaW4="  # noqa: S105


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

    DEVICE_BLOCKED_RESP = {
        "data": {"code": SmartErrorCode.DEVICE_BLOCKED.value, "sec_left": 1685},
        "error_code": SmartErrorCode.SESSION_EXPIRED.value,
    }

    UNENCRYPTED_PASSTHROUGH_BAD_USER_RESP = {
        "error_code": SmartErrorCode.SESSION_EXPIRED.value,
        "result": {
            "data": {
                "code": SmartErrorCode.BAD_USERNAME.value,
                "encrypt_type": ["1", "2"],
                "key": "Someb64keyWithUnknownPurpose",
                "nonce": "MixedCaseAlphaNumericWithUnknownPurpose",
            }
        },
    }

    UNENCRYPTED_PASSTHROUGH_HANDSHAKE_RESP = {
        "error_code": SmartErrorCode.SESSION_EXPIRED.value,
        "result": {
            "data": {
                "code": SmartErrorCode.SESSION_EXPIRED.value,
                "time": 9,
                "max_time": 10,
                "sec_left": 0,
                "encrypt_type": ["1", "2"],
                "key": "Someb64keyWithUnknownPurpose",
                "nonce": "MixedCaseAlphaNumericWithUnknownPurpose",
            }
        },
    }

    UNENCRYPTED_PASSTHROUGH_GOOD_LOGIN_RESPONSE = {
        "error_code": 0,
        "result": {"stok": MOCK_UNENCRYPTED_PASSTHROUGH_STOK, "user_group": "root"},
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
        status_code_list=None,
        want_default_username: bool = False,
        do_not_encrypt_response=False,
        send_response=None,
        sequential_request_delay=0,
        send_error_code=0,
        secure_passthrough_error_code=0,
        digest_password_fail=False,
        device_blocked=False,
        unencrypted_passthrough=False,
    ):
        self.host = host
        self.http_client = HttpClient(DeviceConfig(self.host))
        self.encryption_session: AesEncyptionSession | None = None
        self.server_nonce = secrets.token_bytes(8).hex().upper()
        self.handshake1_complete = False

        # test behaviour attributes
        self.status_code = status_code
        self.status_code_list = status_code_list if status_code_list else []
        self.send_error_code = send_error_code
        self.secure_passthrough_error_code = secure_passthrough_error_code
        self.do_not_encrypt_response = do_not_encrypt_response
        self.want_default_username = want_default_username
        self.digest_password_fail = digest_password_fail
        self.device_blocked = device_blocked
        self.unencrypted_passthrough = unencrypted_passthrough

        self._next_responses: list[dict | bytes] = []

    def _get_status_code(self):
        if self.status_code_list:
            return self.status_code_list.pop(0)
        return self.status_code

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
            if self.unencrypted_passthrough:
                return await self._return_unencrypted_passthrough_login_response(
                    url, json
                )

            return await self._return_handshake2_response(url, json)
        elif method == "securePassthrough":
            assert url == URL(f"https://{self.host}/stok={MOCK_STOCK}/ds")
            return await self._return_secure_passthrough_response(url, json)
        else:
            # The unencrypted passthrough with have actual query method names.
            # This path is also used by the mock class to return unencrypted
            # responses to single 'get' queries which the secure fw returns as unencrypted
            stok = (
                MOCK_UNENCRYPTED_PASSTHROUGH_STOK
                if self.unencrypted_passthrough
                else MOCK_STOCK
            )
            assert url == URL(f"https://{self.host}/stok={stok}/ds")
            return await self._return_send_response(url, json)

    async def _return_handshake1_response(self, url: URL, request: dict[str, Any]):
        request_nonce = request["params"].get("cnonce")
        request_username = request["params"].get("username")

        if self.device_blocked:
            return self._mock_response(self.status_code, self.DEVICE_BLOCKED_RESP)

        if (self.want_default_username and request_username != MOCK_ADMIN_USER) or (
            not self.want_default_username and request_username != MOCK_USER
        ):
            resp = (
                self.UNENCRYPTED_PASSTHROUGH_BAD_USER_RESP
                if self.unencrypted_passthrough
                else self.BAD_USER_RESP
            )
            return self._mock_response(self.status_code, resp)

        device_confirm = SslAesTransport.generate_confirm_hash(
            request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        self.handshake1_complete = True

        if self.unencrypted_passthrough:
            return self._mock_response(
                self._get_status_code(), self.UNENCRYPTED_PASSTHROUGH_HANDSHAKE_RESP
            )

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
        return self._mock_response(self._get_status_code(), resp)

    async def _return_unencrypted_passthrough_login_response(
        self, url: URL, request: dict[str, Any]
    ):
        request_username = request["params"].get("username")
        request_password = request["params"].get("password")
        if (self.want_default_username and request_username != MOCK_ADMIN_USER) or (
            not self.want_default_username and request_username != MOCK_USER
        ):
            return self._mock_response(
                self._get_status_code(), self.UNENCRYPTED_PASSTHROUGH_BAD_USER_RESP
            )

        expected_pwd = _md5_hash(MOCK_PWD.encode())
        if request_password != expected_pwd or self.digest_password_fail:
            return self._mock_response(
                self._get_status_code(), self.UNENCRYPTED_PASSTHROUGH_HANDSHAKE_RESP
            )

        return self._mock_response(
            self._get_status_code(), self.UNENCRYPTED_PASSTHROUGH_GOOD_LOGIN_RESPONSE
        )

    async def _return_handshake2_response(self, url: URL, request: dict[str, Any]):
        request_nonce = request["params"].get("cnonce")
        request_username = request["params"].get("username")
        if (self.want_default_username and request_username != MOCK_ADMIN_USER) or (
            not self.want_default_username and request_username != MOCK_USER
        ):
            return self._mock_response(self._get_status_code(), self.BAD_USER_RESP)

        request_password = request["params"].get("digest_passwd")
        expected_pwd = SslAesTransport.generate_digest_password(
            request_nonce, self.server_nonce, _sha256_hash(MOCK_PWD.encode())
        )
        if request_password != expected_pwd or self.digest_password_fail:
            return self._mock_response(self._get_status_code(), self.BAD_PWD_RESP)

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
        return self._mock_response(self._get_status_code(), resp)

    async def _return_secure_passthrough_response(self, url: URL, json: dict[str, Any]):
        encrypted_request = json["params"]["request"]
        assert self.encryption_session
        decrypted_request = self.encryption_session.decrypt(encrypted_request.encode())
        decrypted_request_dict = json_loads(decrypted_request)

        if self._next_responses:
            next_response = self._next_responses.pop(0)
            if isinstance(next_response, dict):
                decrypted_response_data = json_dumps(next_response).encode()
                encrypted_response = self.encryption_session.encrypt(
                    decrypted_response_data
                )
            else:
                encrypted_response = next_response
        else:
            decrypted_response = await self._post(url, decrypted_request_dict)
            async with decrypted_response:
                decrypted_response_data = await decrypted_response.read()
            encrypted_response = self.encryption_session.encrypt(
                decrypted_response_data
            )

        response = (
            decrypted_response_data
            if self.do_not_encrypt_response
            else encrypted_response
        )
        result = {
            "result": {"response": response.decode()},
            "error_code": self.secure_passthrough_error_code,
        }
        return self._mock_response(self._get_status_code(), result)

    async def _return_send_response(self, url: URL, json: dict[str, Any]):
        result = {"result": {"method": None}, "error_code": self.send_error_code}
        return self._mock_response(self._get_status_code(), result)

    def put_next_response(self, request: dict | bytes) -> None:
        self._next_responses.append(request)
