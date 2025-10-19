"""Implementation of the TPAP SPAKE2+ HTTPS transport.

This transport mirrors the structure and naming of other transports in this
package (handshake -> established -> send), while implementing TP-Link's
TPAP SPAKE2+ (P-256) handshake without DAC and a binary AEAD data channel.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import secrets
import ssl
import struct
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Literal, TypedDict, cast

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import NIST256p, ellipticcurve
from yarl import URL

from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import loads as json_loads

from .basetransport import BaseTransport


class TransportState(Enum):
    """Enum for TPAP state."""

    HANDSHAKE_REQUIRED = auto()
    ESTABLISHED = auto()


_TAG_LEN = 16
_NONCE_LEN = 12
CipherId = Literal["aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"]


class _CipherLabels(TypedDict):
    key_salt: bytes
    key_info: bytes
    nonce_salt: bytes
    nonce_info: bytes
    key_len: int


_LABELS: dict[CipherId, _CipherLabels] = {
    "aes_128_ccm": {
        "key_salt": b"tp-kdf-salt-aes128-key",
        "key_info": b"tp-kdf-info-aes128-key",
        "nonce_salt": b"tp-kdf-salt-aes128-iv",
        "nonce_info": b"tp-kdf-info-aes128-iv",
        "key_len": 16,
    },
    "aes_256_ccm": {
        "key_salt": b"tp-kdf-salt-aes256-key",
        "key_info": b"tp-kdf-info-aes256-key",
        "nonce_salt": b"tp-kdf-salt-aes256-iv",
        "nonce_info": b"tp-kdf-info-aes256-iv",
        "key_len": 32,
    },
    "chacha20_poly1305": {
        "key_salt": b"tp-kdf-salt-chacha20-key",
        "key_info": b"tp-kdf-info-chacha20-key",
        "nonce_salt": b"tp-kdf-salt-chacha20-iv",
        "nonce_info": b"tp-kdf-info-chacha20-iv",
        "key_len": 32,
    },
}


def _hkdf(
    master: bytes,
    *,
    salt: bytes,
    info: bytes,
    length: int,
    algo: str = "SHA256",
) -> bytes:
    algorithm = hashes.SHA256() if algo.upper() == "SHA256" else hashes.SHA512()
    return HKDF(algorithm=algorithm, length=length, salt=salt, info=info).derive(master)


def _nonce(base: bytes, seq: int) -> bytes:
    return base[:-4] + struct.pack(">I", seq)


@dataclass
class _SessionCipher:
    cipher_id: CipherId
    key: bytes
    base_nonce: bytes

    @classmethod
    def from_shared_key(
        cls,
        cipher_id: CipherId,
        shared_key: bytes,
        hkdf_hash: str = "SHA256",
    ) -> _SessionCipher:
        labels = _LABELS[cipher_id]
        return cls(
            cipher_id=cipher_id,
            key=_hkdf(
                shared_key,
                salt=labels["key_salt"],
                info=labels["key_info"],
                length=labels["key_len"],
                algo=hkdf_hash,
            ),
            base_nonce=_hkdf(
                shared_key,
                salt=labels["nonce_salt"],
                info=labels["nonce_info"],
                length=_NONCE_LEN,
                algo=hkdf_hash,
            ),
        )

    def encrypt(self, plaintext: bytes, seq: int) -> bytes:
        n = _nonce(self.base_nonce, seq)
        if self.cipher_id.startswith("aes_"):
            return AESCCM(self.key, tag_length=_TAG_LEN).encrypt(n, plaintext, None)
        return ChaCha20Poly1305(self.key).encrypt(n, plaintext, None)

    def decrypt(self, ciphertext_and_tag: bytes, seq: int) -> bytes:
        n = _nonce(self.base_nonce, seq)
        if self.cipher_id.startswith("aes_"):
            return AESCCM(self.key, tag_length=_TAG_LEN).decrypt(
                n, ciphertext_and_tag, None
            )
        return ChaCha20Poly1305(self.key).decrypt(n, ciphertext_and_tag, None)


class TpapTransport(BaseTransport):
    """TPAP transport using SPAKE2+ (no DAC), structured like other transports.

    Flow:
      - Optional discover (login/discover) to get MAC and offered suites
      - Register (login/pake_register)
      - Prover math (SPAKE2+ P-256 with fixed M/N), confirms
      - Share (login/pake_share), obtain stok and start_seq
      - Secure channel: POST binary frames to /stok={stok}/ds
    """

    DEFAULT_PORT: int = 4433
    CIPHERS = ":".join(
        [
            "AES256-GCM-SHA384",
            "AES256-SHA256",
            "AES128-GCM-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
        ]
    )
    P256_M_COMP = bytes.fromhex(
        "02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f"
    )
    P256_N_COMP = bytes.fromhex(
        "03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49"
    )
    PAKE_CONTEXT_TAG = b"PAKE V1"

    COMMON_HEADERS = {
        "Content-Type": "application/json",
    }

    def __init__(self, *, config: DeviceConfig) -> None:
        super().__init__(config=config)
        self._http_client: HttpClient = HttpClient(config)
        self._ssl_context: ssl.SSLContext | None = None
        self._state = TransportState.HANDSHAKE_REQUIRED
        self._app_url = URL(f"https://{self._host}:{self._port}")
        self._ds_url: URL | None = None
        self._session_id: str | None = None
        self._seq: int | None = None
        self._cipher: _SessionCipher | None = None
        self._curve = NIST256p
        self._G = self._curve.generator
        self._order = self._curve.order
        Mx, My = self._sec1_to_xy(self.P256_M_COMP)
        Nx, Ny = self._sec1_to_xy(self.P256_N_COMP)
        self._M = ellipticcurve.Point(self._curve.curve, Mx, My, self._order)
        self._N = ellipticcurve.Point(self._curve.curve, Nx, Ny, self._order)
        self._discover_mac: str | None = None
        self._discover_suites: list[int] | None = None

    @property
    def default_port(self) -> int:
        """Default port for TPAP transport."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport (unused for TPAP)."""
        return None

    async def send(self, request: str) -> dict[str, Any]:
        """Send a request over the TPAP secure channel."""
        if self._state is TransportState.HANDSHAKE_REQUIRED:
            await self.perform_handshake()
        if self._seq is None or self._cipher is None or self._ds_url is None:
            raise KasaException("TPAP transport is not established")
        seq = self._seq
        frame = struct.pack(">I", seq) + self._cipher.encrypt(request.encode(), seq)
        self._seq += 1
        status, data = await self._http_client.post(
            self._ds_url,
            data=frame,
            ssl=await self._get_ssl_context(),
        )
        if status != 200:
            raise KasaException(
                f"{self._host} responded with unexpected status {status} "
                "on secure request"
            )
        if not isinstance(data, bytes | bytearray):
            self._handle_response_error_code(data, "Error sending TPAP request")
            return cast(dict, data)
        raw = bytes(data)
        if len(raw) < 4 + _TAG_LEN:
            raise KasaException("TPAP response too short")
        rseq = struct.unpack(">I", raw[:4])[0]
        plaintext = self._cipher.decrypt(raw[4:], rseq)
        return cast(dict, json_loads(plaintext.decode()))

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal handshake state."""
        self._state = TransportState.HANDSHAKE_REQUIRED
        self._session_id = None
        self._seq = None
        self._cipher = None
        self._ds_url = None

    async def perform_handshake(self) -> None:
        """Perform SPAKE2+ handshake and initialize the secure channel."""
        await self._perform_discover()
        username = (
            self._config.credentials.username if self._config.credentials else ""
        ) or ""
        passcode = (
            self._config.credentials.password if self._config.credentials else ""
        ) or ""
        suites = self._discover_suites or [2]
        enc_prefs = ["aes_128_ccm", "chacha20_poly1305", "aes_256_ccm"]
        mac = (self._discover_mac or "").upper()
        mac_no_colon = mac.replace(":", "").replace("-", "")
        user_random = os.urandom(16).hex().upper()
        reg = await self._post_login(
            {
                "sub_method": "pake_register",
                "username": username,
                "user_random": user_random,
                "cipher_suites": suites,
                "encryption": enc_prefs,
                "passcode_type": "password",
                "stok": None,
            },
            step_name="register",
        )
        dev_random = reg.get("dev_random") or ""
        dev_salt = reg.get("dev_salt") or ""
        dev_share = reg.get("dev_share") or ""
        suite_type = int(reg.get("cipher_suites") or 2)
        iterations = int(reg.get("iterations") or 10000)
        chosen_cipher = cast(CipherId, reg.get("encryption") or "aes_128_ccm")
        extra_crypt = reg.get("extra_crypt") or {}
        if suites and 0 in suites:
            if not mac:
                raise AuthenticationError(
                    "Device requires MAC-derived passcode (suite 0) "
                    "but device MAC could not be discovered"
                )
            cred_str = self._mac_pass_from_device_mac(mac)
        else:
            cred_str = self._build_credentials(
                extra_crypt, username, passcode, mac_no_colon
            )
        cred = cred_str.encode()
        a, b = self._derive_ab(cred, bytes.fromhex(dev_salt), iterations, 32)
        order = self._order
        w = a % order
        h_scalar = b % order
        G, M, N = self._G, self._M, self._N
        x = self._rand_scalar(order)
        xG = x * G  # type: ignore[operator]
        wM = w * M  # type: ignore[operator]
        Lp = xG + wM  # type: ignore[operator]
        Rx, Ry = self._sec1_to_xy(bytes.fromhex(dev_share))
        R = ellipticcurve.Point(self._curve.curve, Rx, Ry, order)
        Rprime = R + (-(w * N))  # type: ignore[operator]
        Zp = x * Rprime  # type: ignore[operator]
        Vp = (h_scalar % order) * Rprime  # type: ignore[operator]
        L_enc = self._xy_to_uncompressed(Lp.x(), Lp.y())  # type: ignore[operator]
        R_enc = self._xy_to_uncompressed(R.x(), R.y())
        Z_enc = self._xy_to_uncompressed(Zp.x(), Zp.y())  # type: ignore[operator]
        V_enc = self._xy_to_uncompressed(Vp.x(), Vp.y())  # type: ignore[operator]
        M_enc = self._xy_to_uncompressed(M.x(), M.y())  # type: ignore[operator]
        N_enc = self._xy_to_uncompressed(N.x(), N.y())  # type: ignore[operator]
        hash_name = "SHA512" if suite_type == 2 else "SHA256"
        context = (
            self.PAKE_CONTEXT_TAG
            + bytes.fromhex(user_random)
            + bytes.fromhex(dev_random)
        )
        context_hash = self._hash(hash_name, context)
        transcript = (
            self._len8le(context_hash)
            + self._len8le(b"")
            + self._len8le(b"")
            + self._len8le(M_enc)
            + self._len8le(N_enc)
            + self._len8le(L_enc)
            + self._len8le(R_enc)
            + self._len8le(Z_enc)
            + self._len8le(V_enc)
            + self._len8le(self._encode_w(w))
        )
        T = self._hash(hash_name, transcript)
        mac_len = 64 if suite_type == 2 else 32
        conf = self._hkdf_expand("ConfirmationKeys", T, mac_len * 2, hash_name)
        KcA, KcB = conf[:mac_len], conf[mac_len:]
        shared_key = self._hkdf_expand("SharedKey", T, len(T), hash_name)
        user_confirm = self._hmac(hash_name, KcA, R_enc).hex()
        expected_dev_confirm = self._hmac(hash_name, KcB, L_enc).hex()
        share = await self._post_login(
            {
                "sub_method": "pake_share",
                "user_share": L_enc.hex(),
                "user_confirm": user_confirm,
            },
            step_name="share",
        )
        dev_confirm = (share.get("dev_confirm") or "").lower()
        if dev_confirm != expected_dev_confirm.lower():
            raise KasaException("SPAKE2+ confirmation mismatch")
        self._session_id = share.get("stok") or share.get("sessionId")
        self._seq = int(share.get("start_seq") or 1)
        if not self._session_id or self._seq is None:
            raise KasaException("Missing session fields from device")
        self._cipher = _SessionCipher.from_shared_key(
            chosen_cipher, shared_key, hkdf_hash="SHA256"
        )
        self._ds_url = URL(f"{str(self._app_url)}/stok={self._session_id}/ds")
        self._state = TransportState.ESTABLISHED

    async def _perform_discover(self) -> None:
        """Call login/discover to fetch MAC and preferred PAKE suites."""
        if self._discover_mac is not None and self._discover_suites is not None:
            return
        body = {"method": "login", "params": {"sub_method": "discover"}}
        status, data = await self._http_client.post(
            self._app_url.with_path("/"),
            json=body,
            headers=self.COMMON_HEADERS,
            ssl=await self._get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            return

        resp = cast(dict[str, Any], data)
        self._handle_response_error_code(resp, "TPAP discover failed")
        result = resp.get("result") or {}
        self._discover_mac = cast(str | None, result.get("mac")) or None
        tpap = result.get("tpap") or {}
        suites = tpap.get("pake")
        if isinstance(suites, list) and all(isinstance(x, int) for x in suites):
            self._discover_suites = suites

    async def _get_ssl_context(self) -> ssl.SSLContext:
        if not self._ssl_context:
            loop = asyncio.get_running_loop()
            self._ssl_context = await loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def _post_login(
        self,
        params: dict[str, Any],
        *,
        step_name: str,
    ) -> dict[str, Any]:
        body = {"method": "login", "params": params}
        status, data = await self._http_client.post(
            self._app_url.with_path("/"),
            json=body,
            headers=self.COMMON_HEADERS,
            ssl=await self._get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._host} login/{step_name} bad status/body: {status} {type(data)}"
            )
        resp = cast(dict[str, Any], data)
        self._handle_response_error_code(resp, f"TPAP {step_name} failed")
        return cast(dict, resp.get("result") or {})

    def _handle_response_error_code(self, resp_dict: Any, msg: str) -> None:
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except (ValueError, TypeError):
            error_code = SmartErrorCode.SUCCESS
        if error_code is SmartErrorCode.SUCCESS:
            return
        full = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(full, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.HANDSHAKE_REQUIRED
            raise AuthenticationError(full, error_code=error_code)
        raise DeviceError(full, error_code=error_code)

    @staticmethod
    def _sec1_to_xy(sec1: bytes) -> tuple[int, int]:
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sec1)
        nums = pub.public_numbers()
        return nums.x, nums.y

    @staticmethod
    def _xy_to_uncompressed(x: int, y: int) -> bytes:
        numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1())
        pub = numbers.public_key()
        return pub.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

    @staticmethod
    def _hash(alg: str, data: bytes) -> bytes:
        return (
            hashlib.sha512(data).digest()
            if alg.upper() == "SHA512"
            else hashlib.sha256(data).digest()
        )

    @staticmethod
    def _hkdf_expand(label: str, ikm: bytes, out_len: int, alg: str) -> bytes:
        algorithm = hashes.SHA512() if alg.upper() == "SHA512" else hashes.SHA256()
        return HKDF(
            algorithm=algorithm, length=out_len, salt=None, info=label.encode()
        ).derive(ikm)

    @staticmethod
    def _hmac(alg: str, key: bytes, data: bytes) -> bytes:
        return hmac.new(
            key, data, hashlib.sha512 if alg.upper() == "SHA512" else hashlib.sha256
        ).digest()

    @staticmethod
    def _len8le(b: bytes) -> bytes:
        return len(b).to_bytes(8, "little") + b

    @staticmethod
    def _encode_w(w: int) -> bytes:
        wb = w.to_bytes((w.bit_length() + 7) // 8 or 1, "big", signed=False)
        if len(wb) > 1 and len(wb) % 2 == 0 and wb[0] == 0x00:
            wb = wb[1:]
        return wb

    @staticmethod
    def _pbkdf2_sha256(pw: bytes, salt: bytes, iterations: int, length: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", pw, salt, iterations, length)

    @classmethod
    def _derive_ab(
        cls,
        cred: bytes,
        salt: bytes,
        iterations: int,
        hash_len: int = 32,
    ) -> tuple[int, int]:
        iD = hash_len + 8
        out = cls._pbkdf2_sha256(cred, salt, iterations, 2 * iD)
        return int.from_bytes(out[:iD], "big"), int.from_bytes(out[iD:], "big")

    @staticmethod
    def _md5_hex(s: str) -> str:
        # codeql[py/weak-cryptographic-algorithm]:
        # Required by device firmware for credential compatibility.
        # Do not change.
        return hashlib.md5(s.encode()).hexdigest()  # nosec B303  # noqa: S324

    @staticmethod
    def _sha1_hex(s: str) -> str:
        # codeql[py/weak-cryptographic-algorithm]:
        # Required by device firmware for credential compatibility.
        # Do not change.
        return hashlib.sha1(s.encode()).hexdigest()  # nosec B303  # noqa: S324

    @classmethod
    def _authkey_mask(cls, passcode: str, tmpkey: str, dictionary: str) -> str:
        out = []
        L = max(len(tmpkey), len(passcode))
        for i in range(L):
            a = ord(passcode[i]) if i < len(passcode) else 0xBB
            b = ord(tmpkey[i]) if i < len(tmpkey) else 0xBB
            out.append(dictionary[(a ^ b) % len(dictionary)])
        return "".join(out)

    @classmethod
    def _sha1_username_mac_shadow(cls, username: str, mac12hex: str, pwd: str) -> str:
        if (
            not username
            or len(mac12hex) != 12
            or not all(c in "0123456789abcdefABCDEF" for c in mac12hex)
        ):
            return pwd
        mac = ":".join(mac12hex[i : i + 2] for i in range(0, 12, 2)).upper()
        return cls._sha1_hex(cls._md5_hex(username) + "_" + mac)

    @staticmethod
    def _sha256crypt_simple(passcode: str, prefix: str) -> str:
        # codeql[py/weak-cryptographic-algorithm]:
        # Required by device firmware for credential compatibility.
        # Do not change.
        return prefix + "$" + hashlib.sha256(passcode.encode()).hexdigest()  # nosec B303  # noqa: S324

    @classmethod
    def _build_credentials(
        cls,
        extra_crypt: dict | None,
        username: str,
        passcode: str,
        mac_no_colon: str,
    ) -> str:
        """Build the credential string expected by the device firmware.

        Important:
        - The hashing/transform branches herein intentionally mirror vendor formats
          advertised by the device (extra_crypt) for interoperability.
        - These are NOT general-purpose password hashes. Do not change algorithms.
        - Weak-hash usage is explicitly justified and suppressed at call sites.
        """
        if not extra_crypt:
            return (username + "/" + passcode) if username else passcode

        t = (extra_crypt or {}).get("type", "").lower()
        p = (extra_crypt or {}).get("params", {}) or {}

        if t == "password_shadow":
            pid = int(p.get("passwd_id", 0))
            prefix = p.get("passwd_prefix", "") or ""
            if pid == 1:
                return cls._md5_hex(passcode)
            if pid == 2:
                return cls._sha1_hex(passcode)
            if pid == 3:
                return cls._sha1_username_mac_shadow(username, mac_no_colon, passcode)
            if pid == 5:
                return cls._sha256crypt_simple(passcode, prefix)
            return passcode

        if t == "password_authkey":
            tmp = p.get("authkey_tmpkey", "") or ""
            dic = p.get("authkey_dictionary", "") or ""
            return cls._authkey_mask(passcode, tmp, dic) if tmp and dic else passcode

        if t == "password_sha_with_salt":
            sha_name = int(p.get("sha_name", -1))
            sha_salt_b64 = p.get("sha_salt", "") or ""
            try:
                name = "admin" if sha_name == 0 else "user"
                salt_dec = base64.b64decode(sha_salt_b64).decode()
                # codeql[py/weak-cryptographic-algorithm]:
                # Required by device firmware for credential compatibility.
                # Do not change.
                return hashlib.sha256((name + salt_dec + passcode).encode()).hexdigest()  # nosec B303  # noqa: S324
            except Exception:
                return passcode

        return (username + "/" + passcode) if username else passcode

    @staticmethod
    def _mac_pass_from_device_mac(mac_colon: str) -> str:
        mac_hex = mac_colon.replace(":", "").replace("-", "")
        mac_bytes = bytes.fromhex(mac_hex)
        seed = b"GqY5o136oa4i6VprTlMW2DpVXxmfW8"
        ikm = seed + mac_bytes[3:6] + mac_bytes[0:3]
        return (
            HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b"tp-kdf-salt-default-passcode",
                info=b"tp-kdf-info-default-passcode",
            )
            .derive(ikm)
            .hex()
            .upper()
        )

    @staticmethod
    def _rand_scalar(order: int) -> int:
        while True:
            r = secrets.randbelow(order)
            if r != 0:
                return r
