"""Implementation of the TP-Link DLKLAP protocol used by the DL100 smart lock.

DLKLAP is a proprietary variant of KLAP (see ``klaptransport.py``) with two key
differences:

1. It runs over plain **HTTP :80** (never HTTPS to the device).
2. Before the usual handshake1/handshake2 it requires a **cloud-assisted**
   ``handshake0`` step: the client wakes the lock with a challenge derived from
   the TP-Link cloud ``accountId``, the lock returns a ``secret``, and the
   client exchanges that ``secret`` with the TP-Link cloud for a per-session
   ``controlKey``. That control key then plays the role KLAP's ``auth_hash``
   plays in seeding handshake1/handshake2 and the encryption session.

Sequence (all device steps are device-verified on DL100 fw 1.0.17):

    cloud login            -> token, accountId
    handshake0  (device)   -> secret            (wakes the lock radio)
    control-key (cloud)    -> controlKey
    handshake1  (device)   -> R + server_proof  (+ TP_SESSIONID cookie)
    handshake2  (device)   -> 200
    derive lsk/ldk/iv/seq
    /app/request (device)  -> encrypted app-layer calls

Only ONE handshake0 may complete per session -- a second one rotates device
state and invalidates the minted control key (cloud error 15033). All session
establishment is therefore serialized through ``self._handshake_lock``.

Implementation note
-------------------
Unlike the other transports this one uses ``httpx`` directly rather than
``kasa.httpclient.HttpClient``. The raw 33-byte ``handshake0`` body must reach
the device byte-for-byte; wrapping middleware that re-encodes ``text/plain``
binary payloads corrupts it (this is the same reason the TypeScript reference
implementation uses ``node:http`` rather than undici). Migrating to
``HttpClient`` is a possible follow-up once it is confirmed not to mutate the
body.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from typing import Any

import httpx
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    AuthenticationError,
    KasaException,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import loads as json_loads

from .basetransport import BaseTransport

_LOGGER = logging.getLogger(__name__)

# Cloud endpoints.
CLOUD_LOGIN_URL = "https://wap.tplinkcloud.com/"
CONTROL_KEY_URL_FMT = (
    "https://use1-app-server.iot.i.tplinknbu.com/v1/things/{device_id}/control-key"
)

# Networking.
DEFAULT_HTTP_PORT = 80
# Battery locks sleep their radio; the first TCP SYN can be dropped while it
# wakes, so we allow a generous connect timeout and a few handshake0 retries.
CONNECT_TIMEOUT = 15.0
READ_TIMEOUT = 15.0
HANDSHAKE0_RETRIES = 4
HANDSHAKE0_RETRY_DELAY = 2.0

SESSION_COOKIE_NAME = "TP_SESSIONID"


def _sha256(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()  # noqa: S324


class DlklapTransport(BaseTransport):
    """Implementation of the DLKLAP protocol for TP-Link DL100 smart locks.

    Required credentials are the TP-Link **cloud** account username (email) and
    password -- the same account the lock is registered to. The device id is
    resolved from the cloud device list on first connect (see
    :meth:`_ensure_device_id`).
    """

    DEFAULT_PORT: int = DEFAULT_HTTP_PORT
    DEVICE_TYPE: str = "SMART.TAPOLOCK"

    def __init__(self, *, config: DeviceConfig) -> None:
        super().__init__(config=config)

        # Credentials are validated lazily in ``_ensure_login`` rather than here
        # so that construction (e.g. during discovery) never fails; other
        # transports behave the same way.

        # A stable app-instance UUID reused for the lifetime of the transport.
        self._terminal_uuid: str = str(uuid.uuid4()).upper()

        # Cloud-derived state.
        self._token: str | None = None
        self._account_id: str | None = None
        self._device_id: str | None = None

        # Live session state.
        self._session: _DlklapSession | None = None
        self._session_cookie: str | None = None
        self._handshake_done: bool = False
        self._handshake_lock = asyncio.Lock()

        # Persistent HTTP client to the lock. The TP_SESSIONID cookie is
        # connection-scoped, so hs0/hs1/hs2/request must all reuse this client.
        self._lock_client: httpx.AsyncClient | None = None

        # Standard kasa HttpClient, exposed for interface/cleanup compliance
        # and to honour DeviceConfig.http_client. NOTE: the DLKLAP handshake
        # and app requests deliberately use self._lock_client (raw httpx)
        # instead -- the raw 33-byte handshake0 body must not be re-encoded,
        # and the connection-scoped TP_SESSIONID cookie requires every request
        # to share a single client, so app traffic cannot be routed here.
        self._http_client = HttpClient(config=self._config)

        _LOGGER.debug("Created DLKLAP transport for %s", self._host)
        self._base_url = f"http://{self._host}:{self._port}"

    # -- BaseTransport interface --------------------------------------------

    @property
    def default_port(self) -> int:
        """Default port for the transport (DLKLAP is always HTTP :80)."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """Return a stable, non-null credentials hash.

        DLKLAP authenticates against the TP-Link cloud rather than with a
        local KLAP-style auth hash. Returning ``None`` here, however, would
        make :meth:`SmartDevice.update` reject the device up front -- its guard
        raises when both ``credentials`` and ``credentials_hash`` are ``None``
        -- which is inconsistent with the KLAP/AES transports that always
        expose a non-null hash derived from the (possibly empty) credentials.
        The real credential requirement is enforced later in ``_ensure_login``.

        NOTE: this token is deliberately derived from the (non-secret) username
        only. The password must never be fed into a fast hash such as SHA256:
        DLKLAP authenticates against the cloud in ``_ensure_login`` (where a
        wrong password is rejected), so this value exists purely as a stable,
        non-null sentinel and carries no authentication weight.
        """
        username = self._credentials.username if self._credentials else ""
        return _sha256(username.encode()).hex()

    async def send(self, request: str) -> dict[str, Any]:
        """Encrypt ``request``, POST to /app/request, return the decrypted dict.

        On any failure the session is cleared and a single fresh re-handshake is
        attempted before giving up.
        """
        async with self._handshake_lock:
            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    if not self._handshake_done or self._session is None:
                        await self._establish_session()
                    return await self._send_encrypted(request)
                except _RetryableError as ex:
                    last_exc = ex
                    _LOGGER.debug(
                        "DLKLAP send attempt %s to %s failed, resetting session",
                        attempt + 1,
                        self._host,
                    )
                    await self.reset()
            raise KasaException(
                f"DLKLAP request to {self._host} failed after retry"
            ) from last_exc

    async def close(self) -> None:
        """Close the HTTP client and reset internal state."""
        await self.reset()
        client = getattr(self, "_lock_client", None)
        self._lock_client = None
        if client is not None:
            await client.aclose()
        http_client = getattr(self, "_http_client", None)
        if http_client is not None:
            await http_client.close()

    async def reset(self) -> None:
        """Reset handshake/session state (keeps the cloud token)."""
        self._handshake_done = False
        self._session = None
        self._session_cookie = None

    # -- Session establishment ----------------------------------------------

    async def _establish_session(self) -> None:
        """Full handshake0 -> control-key -> handshake1/2 -> derive keys."""
        _LOGGER.debug("Starting DLKLAP handshake with %s", self._host)
        await self.reset()

        await self._ensure_login()
        await self._ensure_device_id()

        lock_client = self._get_lock_client()
        rand4 = secrets.token_bytes(4)
        secret = await self._handshake0(lock_client, rand4)
        control_key = await self._fetch_control_key(secret, rand4)
        local_seed, remote_seed, lmk = await self._handshake1(lock_client, control_key)
        await self._handshake2(lock_client, local_seed, remote_seed, lmk)

        self._session = _DlklapSession(local_seed, remote_seed, lmk)
        self._handshake_done = True
        _LOGGER.debug("DLKLAP handshake with %s complete", self._host)

    def _get_lock_client(self) -> httpx.AsyncClient:
        if self._lock_client is None:
            timeout = httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)
            # verify=False: the device speaks plain HTTP, no TLS involved.
            self._lock_client = httpx.AsyncClient(timeout=timeout, verify=False)  # noqa: S501
        return self._lock_client

    def _lock_headers(self, *, with_cookie: bool = False) -> dict[str, str]:
        headers = {
            "Content-Type": "text/plain",
            "Referer": f"{self._base_url}/",
            "Accept": "application/json",
            "requestByApp": "true",
        }
        if with_cookie and self._session_cookie:
            headers["Cookie"] = self._session_cookie
        return headers

    # -- Step 1: cloud login ------------------------------------------------

    async def _ensure_login(self) -> None:
        if self._token and self._account_id:
            return
        _LOGGER.debug("DLKLAP cloud login")
        if not self._credentials or not self._credentials.username:
            raise AuthenticationError(
                "DLKLAP requires TP-Link cloud credentials "
                "(username/email and password)."
            )
        async with httpx.AsyncClient(timeout=READ_TIMEOUT, verify=True) as client:
            resp = await client.post(
                CLOUD_LOGIN_URL,
                json={
                    "method": "login",
                    "params": {
                        "appType": "Tapo_Android",
                        "cloudUserName": self._credentials.username,
                        "cloudPassword": self._credentials.password,
                        "terminalUUID": self._terminal_uuid,
                        "refreshTokenNeeded": False,
                    },
                },
            )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error_code", -1) != 0:
            raise AuthenticationError(
                f"DLKLAP cloud login failed: {body.get('msg', body)}"
            )
        self._token = body["result"]["token"]
        self._account_id = body["result"]["accountId"]

    async def _ensure_device_id(self) -> None:
        """Resolve the cloud device id for this lock.

        NOTE: not yet device-verified. The cloud device list does not expose the
        device LAN IP, so when the account owns more than one lock we cannot
        reliably match by ``self._host``. For now we pick the single
        ``SMART.TAPOLOCK`` device if there is exactly one; otherwise an explicit
        override must be supplied. This should be revisited before merge.
        """
        if self._device_id:
            return
        if self._token is None:
            raise KasaException(
                "DLKLAP: cloud login required before resolving device id"
            )
        _LOGGER.debug("DLKLAP resolving device id from cloud device list")
        async with httpx.AsyncClient(timeout=READ_TIMEOUT, verify=True) as client:
            resp = await client.post(
                CLOUD_LOGIN_URL,
                params={"token": self._token},
                json={"method": "getDeviceList"},
            )
        resp.raise_for_status()
        body = resp.json()
        if body.get("error_code", -1) != 0:
            raise KasaException(f"getDeviceList failed: {body.get('msg', body)}")
        devices = body.get("result", {}).get("deviceList", [])
        locks = [d for d in devices if d.get("deviceType") == self.DEVICE_TYPE]
        if len(locks) == 1:
            self._device_id = locks[0]["deviceId"]
        elif not locks:
            raise KasaException(
                f"No {self.DEVICE_TYPE} device found in the cloud account"
            )
        else:
            raise KasaException(
                "Multiple locks found; DLKLAP device-id auto-resolution cannot "
                "yet disambiguate by IP. Supply the device id explicitly."
            )

    # -- Step 2: handshake0 -------------------------------------------------

    async def _handshake0(self, lock_client: httpx.AsyncClient, rand4: bytes) -> str:
        """Wake the lock and obtain the 236-char base64 ``secret``.

        Body is 33 raw bytes: sha((hex(rand4)+accountId).upper())[:32] + 0x00.
        """
        if self._account_id is None:
            raise KasaException("DLKLAP: cloud login required before handshake0")
        hash_input = (rand4.hex() + self._account_id).upper().encode("ascii")
        body = _sha256(hash_input) + b"\x00"  # 32 + 1 = 33 bytes

        last_exc: Exception | None = None
        for attempt in range(1, HANDSHAKE0_RETRIES + 1):
            try:
                resp = await lock_client.post(
                    f"{self._base_url}/app/handshake0",
                    content=body,
                    headers=self._lock_headers(),
                )
                resp.raise_for_status()
                return resp.text.strip()
            except (
                httpx.ConnectTimeout,
                httpx.ConnectError,
                httpx.ReadTimeout,
            ) as ex:
                last_exc = ex
                _LOGGER.debug(
                    "handshake0 attempt %s/%s to %s failed (%s), lock may be waking",
                    attempt,
                    HANDSHAKE0_RETRIES,
                    self._host,
                    type(ex).__name__,
                )
                await asyncio.sleep(HANDSHAKE0_RETRY_DELAY)
        raise _RetryableError(
            f"handshake0 could not reach {self._host} after "
            f"{HANDSHAKE0_RETRIES} attempts: {last_exc!r}"
        )

    # -- Step 3: cloud control-key ------------------------------------------

    async def _fetch_control_key(self, secret: str, rand4: bytes) -> str:
        """Exchange the handshake0 ``secret`` for a per-session control key."""
        if self._token is None or self._device_id is None:
            raise KasaException(
                "DLKLAP: login and device id required before control-key exchange"
            )
        url = CONTROL_KEY_URL_FMT.format(device_id=self._device_id)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"ut|{self._token}",
            "app-cid": f"app:Tapo_Android:{self._terminal_uuid}",
            "App-Type": "Tapo_Android",
            "x-app-name": "Tapo_Android",
            "UUID": self._terminal_uuid,
            "Terminal-Id": self._terminal_uuid,
            "x-term-id": self._terminal_uuid,
            "Platform": "ANDROID",
            "X-App-Os": "android",
        }
        # This host presents TP-Link's PRIVATE CA (not a public root), so TLS
        # verification must be disabled for THIS call only. The login call above
        # carries the account password and stays fully verified.
        async with httpx.AsyncClient(timeout=READ_TIMEOUT, verify=False) as client:  # noqa: S501
            resp = await client.post(
                url,
                json={"secret": secret, "random": rand4.hex().upper()},
                headers=headers,
            )
        resp.raise_for_status()
        body = resp.json()
        control_key = body.get("controlKey")
        if not control_key:
            raise AuthenticationError(f"Cloud did not return a controlKey: {body}")
        return control_key

    # -- Step 4: handshake1 -------------------------------------------------

    async def _handshake1(
        self, lock_client: httpx.AsyncClient, control_key: str
    ) -> tuple[bytes, bytes, bytes]:
        """Verify the device and capture the session cookie.

        Returns ``(local_seed, remote_seed, lmk)`` where ``lmk = sha(ck)``.
        """
        ck = control_key.upper().encode("ascii")  # 64 ASCII bytes
        lmk = _sha256(ck)
        local_seed = secrets.token_bytes(16)
        body = local_seed + _sha256(local_seed + ck)  # 16 + 32 = 48 bytes

        resp = await lock_client.post(
            f"{self._base_url}/app/handshake1",
            content=body,
            headers=self._lock_headers(),
        )
        resp.raise_for_status()
        raw = resp.content
        if len(raw) != 48:
            raise KasaException(
                f"handshake1 from {self._host} returned {len(raw)} bytes, expected 48"
            )
        remote_seed = raw[:16]
        server_proof = raw[16:]

        expected = _sha256(local_seed + remote_seed + _sha256(ck))
        if expected != server_proof:
            raise AuthenticationError(
                f"handshake1 server proof mismatch from {self._host}; the "
                "control key is wrong or stale."
            )

        cookie = self._extract_session_cookie(resp)
        if not cookie:
            raise KasaException(
                f"handshake1 from {self._host} did not set {SESSION_COOKIE_NAME}"
            )
        self._session_cookie = cookie
        return local_seed, remote_seed, lmk

    @staticmethod
    def _extract_session_cookie(resp: httpx.Response) -> str | None:
        raw = resp.headers.get("set-cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(f"{SESSION_COOKIE_NAME}="):
                return part
        return None

    # -- Step 5: handshake2 -------------------------------------------------

    async def _handshake2(
        self,
        lock_client: httpx.AsyncClient,
        local_seed: bytes,
        remote_seed: bytes,
        lmk: bytes,
    ) -> None:
        body = _sha256(remote_seed + local_seed + lmk)  # 32 bytes
        resp = await lock_client.post(
            f"{self._base_url}/app/handshake2",
            content=body,
            headers=self._lock_headers(with_cookie=True),
        )
        resp.raise_for_status()

    # -- Step 7: encrypted request ------------------------------------------

    async def _send_encrypted(self, request: str) -> dict[str, Any]:
        if self._session is None:
            raise KasaException("DLKLAP: no active session")
        lock_client = self._get_lock_client()
        payload, seq = self._session.encrypt(request.encode())
        try:
            resp = await lock_client.post(
                f"{self._base_url}/app/request",
                params={"seq": seq},
                content=payload,
                headers=self._lock_headers(with_cookie=True),
            )
        except (httpx.ConnectError, httpx.TimeoutException) as ex:
            raise _RetryableError(
                f"DLKLAP request transport error to {self._host}: {ex!r}"
            ) from ex

        if resp.status_code == 403:
            # Security/session error -- force a fresh handshake next time.
            raise _RetryableError(
                f"Got HTTP 403 from {self._host}; session likely expired"
            )
        if resp.status_code != 200:
            raise KasaException(
                f"Device {self._host} responded with {resp.status_code} to "
                f"request with seq {seq}"
            )

        try:
            decrypted = self._session.decrypt(resp.content)
        except Exception as ex:  # noqa: BLE001
            raise KasaException(
                f"Error decrypting response from {self._host}: {ex}"
            ) from ex
        return json_loads(decrypted)


class _DlklapSession:
    """Encryption session state for DLKLAP (mirrors ``KlapEncryptionSession``).

    Holds the derived keys and the request sequence number, which the device
    expects to increment by one on every request.
    """

    def __init__(self, local_seed: bytes, remote_seed: bytes, lmk: bytes) -> None:
        self._local_seed = local_seed
        self._remote_seed = remote_seed
        self._lmk = lmk
        self._lsk = self._kdf(b"lsk")[:16]  # AES-128 key
        self._ldk = self._kdf(b"ldk")[:28]  # MAC key
        iv_full = self._kdf(b"iv")
        self._ivb = iv_full[:12]  # 12-byte IV base
        self._seq = int.from_bytes(iv_full[28:32], "big") & 0x7FFFFFFF
        self._aes = algorithms.AES(self._lsk)

    def _kdf(self, tag: bytes) -> bytes:
        return _sha256(tag + self._local_seed + self._remote_seed + self._lmk)

    def encrypt(self, msg: bytes) -> tuple[bytes, int]:
        """Encrypt ``msg`` and increment the sequence number.

        Returns ``(mac + ciphertext, seq)``. The MAC uses the 4-byte seq form
        (NOT the full IV): ``sha(ldk + seq4 + ciphertext)``.
        """
        self._seq += 1
        seq_b = self._seq.to_bytes(4, "big")
        iv = self._ivb + seq_b  # 16-byte IV
        cipher = Cipher(self._aes, modes.CBC(iv))
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded = padder.update(msg) + padder.finalize()
        ciphertext = encryptor.update(padded) + encryptor.finalize()
        mac = _sha256(self._ldk + seq_b + ciphertext)
        return mac + ciphertext, self._seq

    def decrypt(self, msg: bytes) -> str:
        """Decrypt a response body (first 32 bytes are the MAC).

        The DL100 prefixes the JSON with a few bytes, so we return the substring
        from the first ``{`` onward.
        """
        seq_b = self._seq.to_bytes(4, "big")
        iv = self._ivb + seq_b
        cipher = Cipher(self._aes, modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(msg[32:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        start = plaintext.index(ord("{"))
        return plaintext[start:].decode()
