"""Unit tests for :mod:`kasa.transports.dlklaptransport`.

DLKLAP is almost entirely network I/O (cloud login, device-id resolution,
handshake0/1/2, encrypted /app/request), so nothing in it runs under the
normal fixture-driven test suite. These tests mock ``httpx`` at the
``AsyncClient`` boundary and drive the *real* handshake + crypto code paths.

The fake "device" side deliberately reuses the transport's own ``_sha256`` and
``_DlklapSession`` so the handshake proof and the AES-CBC/MAC round-trip are
correct by construction (no reimplementation of crypto to drift out of sync).
"""

from __future__ import annotations

import json

import httpx
import pytest

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.exceptions import AuthenticationError, KasaException, _RetryableError
from kasa.transports.dlklaptransport import (
    SESSION_COOKIE_NAME,
    DlklapTransport,
    _DlklapSession,
    _sha256,
)

# NOTE: the transport never inspects device_family/encryption_type, so any
# valid combination works here. Swap these for the lock's real family/encryption
# if you prefer the fixture to mirror production wiring exactly.
_CONNECTION_TYPE = DeviceConnectionParameters(
    device_family=DeviceFamily.SmartTapoPlug,
    encryption_type=DeviceEncryptionType.Klap,
    https=False,
)


def _make_config(*, username: str | None = "user@example.com") -> DeviceConfig:
    credentials = (
        Credentials(username, "correct horse battery staple")
        if username is not None
        else None
    )
    return DeviceConfig(
        host="127.0.0.1",
        credentials=credentials,
        connection_type=_CONNECTION_TYPE,
    )


def _make_transport(**kwargs) -> DlklapTransport:
    return DlklapTransport(config=_make_config(**kwargs))


# ---------------------------------------------------------------------------
# Fake httpx layer
# ---------------------------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for :class:`httpx.Response`."""

    def __init__(
        self,
        status_code: int = 200,
        *,
        content: bytes = b"",
        text: str | None = None,
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self._content = content
        self._text = text
        self._json = json_data
        self.headers = headers or {}

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        return self._text if self._text is not None else self._content.decode()

    def json(self) -> dict:
        assert self._json is not None
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "http://device/"),
                response=httpx.Response(self.status_code),
            )


class FakeBackend:
    """Stateful fake cloud + lock device with per-test error injection knobs."""

    def __init__(self) -> None:
        self.token = "cloud-token"  # noqa: S105 - fake cloud token for tests
        self.account_id = "ACCOUNT123"
        self.device_id = "DEVICE123"
        self.control_key: str | None = "K" * 64
        self.secret = "c2VjcmV0" * 30  # arbitrary base64-ish blob
        self.remote_seed = bytes(range(16))
        self.response_payload = {"error_code": 0, "result": {"foo": "bar"}}

        # Captured during handshake1 so /app/request can build a matching session.
        self.local_seed: bytes | None = None
        # Persistent device-side session, created at handshake1 and advanced in
        # lockstep with the transport so multi-request sequences stay aligned.
        self.device_session: _DlklapSession | None = None

        # Error-injection knobs.
        self.login_error = False
        self.device_mode = "single"  # "single" | "none" | "multiple"
        self.hs0_exc: Exception | None = None
        self.hs1_mode = "ok"  # "ok" | "badlen" | "badproof" | "nocookie"
        self.request_status = 200
        self.request_bad_body = False

    # -- routing ----------------------------------------------------------

    def handle(self, url, *, content, json_body, params, headers) -> FakeResponse:
        if "tplinkcloud" in url:
            method = (json_body or {}).get("method")
            if method == "login":
                return self._login()
            if method == "getDeviceList":
                return self._device_list()
        if "control-key" in url:
            return self._control_key()
        if "handshake0" in url:
            return self._handshake0()
        if "handshake1" in url:
            return self._handshake1(content)
        if "handshake2" in url:
            return FakeResponse(200, content=b"")
        if "/app/request" in url:
            return self._request()
        raise AssertionError(f"unexpected URL in fake backend: {url!r}")

    # -- cloud ------------------------------------------------------------

    def _login(self) -> FakeResponse:
        if self.login_error:
            return FakeResponse(
                200, json_data={"error_code": -20601, "msg": "Incorrect password"}
            )
        return FakeResponse(
            200,
            json_data={
                "error_code": 0,
                "result": {"token": self.token, "accountId": self.account_id},
            },
        )

    def _device_list(self) -> FakeResponse:
        lock = {"deviceType": DlklapTransport.DEVICE_TYPE, "deviceId": self.device_id}
        if self.device_mode == "none":
            devices = [{"deviceType": "SMART.TAPOPLUG", "deviceId": "PLUG"}]
        elif self.device_mode == "multiple":
            devices = [lock, {**lock, "deviceId": "DEVICE456"}]
        else:
            devices = [lock, {"deviceType": "SMART.TAPOPLUG", "deviceId": "PLUG"}]
        return FakeResponse(
            200, json_data={"error_code": 0, "result": {"deviceList": devices}}
        )

    def _control_key(self) -> FakeResponse:
        if self.control_key is None:
            return FakeResponse(200, json_data={"error_code": 0})
        return FakeResponse(200, json_data={"controlKey": self.control_key})

    # -- device -----------------------------------------------------------

    def _handshake0(self) -> FakeResponse:
        if self.hs0_exc is not None:
            raise self.hs0_exc
        return FakeResponse(200, text=self.secret)

    def _handshake1(self, content: bytes) -> FakeResponse:
        local_seed = content[:16]
        self.local_seed = local_seed
        if self.hs1_mode == "badlen":
            return FakeResponse(200, content=b"\x00" * 10)
        assert self.control_key is not None
        ck = self.control_key.upper().encode("ascii")
        if self.hs1_mode == "badproof":
            proof = b"\x00" * 32
        else:
            proof = _sha256(local_seed + self.remote_seed + _sha256(ck))
        body = self.remote_seed + proof
        headers = {}
        if self.hs1_mode != "nocookie":
            headers["set-cookie"] = f"{SESSION_COOKIE_NAME}=abc123; Path=/; HttpOnly"
        if self.hs1_mode == "ok":
            # Mirror the transport's session exactly (same seeds -> same seq0).
            self.device_session = _DlklapSession(
                local_seed, self.remote_seed, _sha256(ck)
            )
        return FakeResponse(200, content=body, headers=headers)

    def _request(self) -> FakeResponse:
        if self.request_status != 200:
            return FakeResponse(self.request_status, content=b"")
        if self.request_bad_body:
            return FakeResponse(200, content=b"\x00" * 48)
        # Encrypt with the persistent device session so its sequence number
        # advances in lockstep with the transport across repeated requests.
        assert self.device_session is not None
        payload, _seq = self.device_session.encrypt(
            json.dumps(self.response_payload).encode()
        )
        return FakeResponse(200, content=payload)


class FakeAsyncClient:
    """Stand-in for :class:`httpx.AsyncClient` backed by a shared FakeBackend."""

    def __init__(self, backend: FakeBackend) -> None:
        self._backend = backend
        self.closed = False

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(
        self, url, *, content=None, json=None, params=None, headers=None
    ) -> FakeResponse:
        return self._backend.handle(
            url, content=content, json_body=json, params=params, headers=headers
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def patch_httpx(mocker, backend):
    """Patch httpx.AsyncClient so every client shares the one backend.

    ``httpx.Timeout`` and the exception classes are left intact.
    """
    mocker.patch(
        "kasa.transports.dlklaptransport.httpx.AsyncClient",
        side_effect=lambda *a, **k: FakeAsyncClient(backend),
    )
    # Kill the retry backoff sleep so retry paths run instantly.
    mocker.patch("kasa.transports.dlklaptransport.asyncio.sleep", return_value=None)
    return backend


# ---------------------------------------------------------------------------
# Pure logic (no network)
# ---------------------------------------------------------------------------


async def test_credentials_hash_ignores_password():
    """The credentials hash is a non-secret sentinel derived from username only."""
    t1 = DlklapTransport(
        config=DeviceConfig(
            host="127.0.0.1",
            credentials=Credentials("user@example.com", "password-one"),
            connection_type=_CONNECTION_TYPE,
        )
    )
    t2 = DlklapTransport(
        config=DeviceConfig(
            host="127.0.0.1",
            credentials=Credentials("user@example.com", "password-two"),
            connection_type=_CONNECTION_TYPE,
        )
    )
    assert t1.credentials_hash == t2.credentials_hash
    assert t1.credentials_hash == _sha256(b"user@example.com").hex()


async def test_credentials_hash_without_credentials():
    t = _make_transport(username=None)
    assert t.credentials_hash == _sha256(b"").hex()


async def test_default_port_uses_override():
    config = DeviceConfig(
        host="127.0.0.1",
        credentials=Credentials("u", "p"),
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartTapoPlug,
            encryption_type=DeviceEncryptionType.Klap,
            https=False,
            http_port=8080,
        ),
    )
    assert DlklapTransport(config=config).default_port == 8080


async def test_default_port_falls_back_to_80():
    assert _make_transport().default_port == 80


async def test_lock_headers_cookie_toggle():
    t = _make_transport()
    assert "Cookie" not in t._lock_headers()
    t._session_cookie = f"{SESSION_COOKIE_NAME}=abc"
    assert t._lock_headers(with_cookie=True)["Cookie"] == f"{SESSION_COOKIE_NAME}=abc"
    # No stored cookie -> header omitted even when requested.
    t._session_cookie = None
    assert "Cookie" not in t._lock_headers(with_cookie=True)


def test_extract_session_cookie():
    resp = FakeResponse(
        200,
        headers={"set-cookie": f"{SESSION_COOKIE_NAME}=xyz; Path=/; HttpOnly"},
    )
    assert DlklapTransport._extract_session_cookie(resp) == f"{SESSION_COOKIE_NAME}=xyz"
    assert DlklapTransport._extract_session_cookie(FakeResponse(200)) is None


def test_session_encrypt_decrypt_roundtrip():
    session = _DlklapSession(b"L" * 16, b"R" * 16, b"M" * 32)
    plaintext = '{"error_code": 0, "result": {"hello": "world"}}'
    payload, seq = session.encrypt(plaintext.encode())
    assert seq == session._seq  # encrypt advanced the sequence
    # The device echoes at the same seq the request advanced to.
    assert session.decrypt(payload) == plaintext


# ---------------------------------------------------------------------------
# Happy path through the public API
# ---------------------------------------------------------------------------


async def test_send_happy_path(patch_httpx):
    backend = patch_httpx
    transport = _make_transport()
    result = await transport.send('{"get_device_info": {}}')
    assert result == backend.response_payload
    assert transport._handshake_done is True
    assert transport._token == backend.token
    assert transport._device_id == backend.device_id
    await transport.close()


async def test_send_reuses_existing_session(patch_httpx, mocker):
    transport = _make_transport()
    await transport.send('{"get_device_info": {}}')
    spy = mocker.spy(transport, "_establish_session")
    await transport.send('{"get_device_info": {}}')
    spy.assert_not_called()


# ---------------------------------------------------------------------------
# Cloud login / device-id resolution
# ---------------------------------------------------------------------------


async def test_ensure_login_requires_credentials():
    transport = _make_transport(username=None)
    with pytest.raises(AuthenticationError, match="cloud credentials"):
        await transport._ensure_login()


async def test_ensure_login_cloud_error(patch_httpx):
    patch_httpx.login_error = True
    transport = _make_transport()
    with pytest.raises(AuthenticationError, match="cloud login failed"):
        await transport._ensure_login()


async def test_ensure_login_is_cached(patch_httpx):
    transport = _make_transport()
    transport._token = "cached"  # noqa: S105 - not a real secret
    transport._account_id = "cached-account"
    await transport._ensure_login()  # returns early, no network
    assert transport._token == "cached"  # noqa: S105 - not a real secret


async def test_ensure_device_id_none(patch_httpx):
    patch_httpx.device_mode = "none"
    transport = _make_transport()
    transport._token = patch_httpx.token
    with pytest.raises(KasaException, match="No .* device found"):
        await transport._ensure_device_id()


async def test_ensure_device_id_multiple(patch_httpx):
    patch_httpx.device_mode = "multiple"
    transport = _make_transport()
    transport._token = patch_httpx.token
    with pytest.raises(KasaException, match="Multiple locks"):
        await transport._ensure_device_id()


async def test_ensure_device_id_requires_login():
    transport = _make_transport()
    with pytest.raises(KasaException, match="cloud login required"):
        await transport._ensure_device_id()


# ---------------------------------------------------------------------------
# handshake0 / control-key
# ---------------------------------------------------------------------------


async def test_handshake0_requires_account_id():
    transport = _make_transport()
    with pytest.raises(KasaException, match="cloud login required before handshake0"):
        await transport._handshake0(FakeAsyncClient(FakeBackend()), b"\x00\x00\x00\x00")


async def test_handshake0_retries_then_raises(patch_httpx):
    patch_httpx.hs0_exc = httpx.ConnectError("lock asleep")
    transport = _make_transport()
    transport._account_id = patch_httpx.account_id
    client = transport._get_lock_client()
    with pytest.raises(_RetryableError, match="handshake0 could not reach"):
        await transport._handshake0(client, b"\x01\x02\x03\x04")


async def test_fetch_control_key_missing(patch_httpx):
    patch_httpx.control_key = None
    transport = _make_transport()
    transport._token = patch_httpx.token
    transport._device_id = patch_httpx.device_id
    with pytest.raises(AuthenticationError, match="did not return a controlKey"):
        await transport._fetch_control_key("secret", b"\x01\x02\x03\x04")


async def test_fetch_control_key_requires_login():
    transport = _make_transport()
    with pytest.raises(KasaException, match="login and device id required"):
        await transport._fetch_control_key("secret", b"\x01\x02\x03\x04")


# ---------------------------------------------------------------------------
# handshake1 error branches
# ---------------------------------------------------------------------------


async def test_handshake1_wrong_length(patch_httpx):
    patch_httpx.hs1_mode = "badlen"
    transport = _make_transport()
    client = transport._get_lock_client()
    with pytest.raises(KasaException, match="expected 48"):
        await transport._handshake1(client, patch_httpx.control_key)


async def test_handshake1_proof_mismatch(patch_httpx):
    patch_httpx.hs1_mode = "badproof"
    transport = _make_transport()
    client = transport._get_lock_client()
    with pytest.raises(AuthenticationError, match="server proof mismatch"):
        await transport._handshake1(client, patch_httpx.control_key)


async def test_handshake1_missing_cookie(patch_httpx):
    patch_httpx.hs1_mode = "nocookie"
    transport = _make_transport()
    client = transport._get_lock_client()
    with pytest.raises(KasaException, match=SESSION_COOKIE_NAME):
        await transport._handshake1(client, patch_httpx.control_key)


# ---------------------------------------------------------------------------
# Encrypted request error branches / retry
# ---------------------------------------------------------------------------


async def test_send_403_forces_rehandshake_then_fails(patch_httpx):
    patch_httpx.request_status = 403
    transport = _make_transport()
    with pytest.raises(KasaException, match="failed after retry"):
        await transport.send('{"get_device_info": {}}')


async def test_send_non_200(patch_httpx):
    patch_httpx.request_status = 500
    transport = _make_transport()
    with pytest.raises(KasaException, match="responded with 500"):
        await transport.send('{"get_device_info": {}}')


async def test_send_decrypt_failure(patch_httpx):
    patch_httpx.request_bad_body = True
    transport = _make_transport()
    with pytest.raises(KasaException, match="decrypting response"):
        await transport.send('{"get_device_info": {}}')


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_reset_clears_session_state(patch_httpx):
    transport = _make_transport()
    await transport.send('{"get_device_info": {}}')
    assert transport._session is not None
    await transport.reset()
    assert transport._session is None
    assert transport._session_cookie is None
    assert transport._handshake_done is False


async def test_close_closes_lock_client(patch_httpx):
    transport = _make_transport()
    await transport.send('{"get_device_info": {}}')
    lock_client = transport._lock_client
    await transport.close()
    assert transport._lock_client is None
    assert lock_client.closed is True
