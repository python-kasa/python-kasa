"""Implementation of the TP-Link TPAP protocol using SPAKE2+ only."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import os
import secrets
import ssl
import struct
from datetime import UTC, datetime
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from ecdsa import NIST256p, NIST384p, NIST521p, ellipticcurve
from ecdsa.curves import Curve
from ecdsa.ellipticcurve import CurveFp, PointJacobi
from passlib.hash import md5_crypt, sha256_crypt
from yarl import URL

from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _ConnectionError,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import loads as json_loads
from kasa.transports import BaseTransport

_LOGGER = logging.getLogger(__name__)


class TransportState(Enum):
    """State for TPAP transport handshake and session lifecycle."""

    ESTABLISHED = auto()
    NOT_ESTABLISHED = auto()


class TpapEncryptionSession:
    """Handle TPAP SPAKE2+ discovery, handshake, and AEAD session state."""

    PAKE_CONTEXT_TAG = b"PAKE V1"
    TAG_LEN = 16
    NONCE_LEN = 12
    CIPHER_PARAMETERS = {
        "aes_128_ccm": (
            b"tp-kdf-salt-aes128-key",
            b"tp-kdf-info-aes128-key",
            b"tp-kdf-salt-aes128-iv",
            b"tp-kdf-info-aes128-iv",
            16,
        ),
        "aes_256_ccm": (
            b"tp-kdf-salt-aes256-key",
            b"tp-kdf-info-aes256-key",
            b"tp-kdf-salt-aes256-iv",
            b"tp-kdf-info-aes256-iv",
            32,
        ),
        "chacha20_poly1305": (
            b"tp-kdf-salt-chacha20-key",
            b"tp-kdf-info-chacha20-key",
            b"tp-kdf-salt-chacha20-iv",
            b"tp-kdf-info-chacha20-iv",
            32,
        ),
    }

    def __init__(self, transport: TpapTransport) -> None:
        self._transport = transport
        self._handshake_lock = asyncio.Lock()
        self._device_mac: str = ""
        self._tpap_tls: int | None = None
        self._tpap_port: int | None = None
        self._tpap_dac: bool = False
        self._tpap_pake: list[int] = []
        self._tpap_user_hash_type: int | None = None
        self._session_id: str | None = None
        self._sequence: int | None = None
        self._ds_url: URL | None = None
        self._cipher_id: str = "aes_128_ccm"
        self._hkdf_hash: str = "SHA256"
        self._key: bytes | None = None
        self._base_nonce: bytes | None = None
        self._shared_key: bytes | None = None
        self._expected_dev_confirm: str | None = None
        self._dac_nonce_base64: str | None = None
        self._user_random: str | None = None
        self.reset()

    @property
    def _uses_smartcam_auth(self) -> bool:
        return self._transport.USE_SMARTCAM_AUTH

    @property
    def tls_mode(self) -> int | None:
        """Return the discovered TLS mode."""
        return self._tpap_tls

    @property
    def ds_url(self) -> URL | None:
        """Return the secure DS endpoint for the current session."""
        return self._ds_url

    @property
    def device_mac(self) -> str:
        """Return the discovered device MAC."""
        return self._device_mac

    @property
    def is_established(self) -> bool:
        """Return true when handshake and session keys are ready."""
        return (
            self._session_id is not None
            and self._sequence is not None
            and self._ds_url is not None
            and self._key is not None
            and self._base_nonce is not None
        )

    def reset(self) -> None:
        """Reset discovered metadata and established session state."""
        self._transport._ssl_context = None
        self._transport._state = TransportState.NOT_ESTABLISHED
        self._transport._app_url = self._transport._get_initial_app_url()
        self._device_mac = self._transport._known_device_mac
        self._tpap_tls = self._transport._known_tpap_tls
        self._tpap_port = self._transport._known_tpap_port
        self._tpap_dac = self._transport._known_tpap_dac
        self._tpap_pake = list(self._transport._known_tpap_pake)
        self._tpap_user_hash_type = self._transport._known_tpap_user_hash_type
        self._session_id = None
        self._sequence = None
        self._ds_url = None
        self._cipher_id = "aes_128_ccm"
        self._hkdf_hash = "SHA256"
        self._key = None
        self._base_nonce = None
        self._shared_key = None
        self._expected_dev_confirm = None
        self._dac_nonce_base64 = None
        self._user_random = None

    @staticmethod
    def _parse_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_result_dict(response: dict[str, Any], context: str) -> dict[str, Any]:
        result = response.get("result")
        if not isinstance(result, dict):
            raise KasaException(f"{context} missing result object")
        result_dict: dict[str, Any] = result
        return result_dict

    @staticmethod
    def _require_int_field(value: Any, *, field: str, context: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise KasaException(f"{context} has invalid {field}") from exc

    async def perform_handshake(self) -> None:
        """Run discovery and SPAKE2+ handshake exactly once per session."""
        async with self._handshake_lock:
            if self.is_established:
                self._transport._state = TransportState.ESTABLISHED
                return

            self.reset()
            _LOGGER.debug(
                "TPAP: starting SPAKE2+ handshake with %s",
                self._transport._host,
            )

            await self._discover()
            await self._perform_spake_handshake()

            self._transport._state = TransportState.ESTABLISHED
            _LOGGER.debug("TPAP: handshake complete with %s", self._transport._host)

    async def _discover(self) -> None:
        body = {"method": "login", "params": {"sub_method": "discover"}}
        status, data = await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=await self._transport.get_ssl_context(),
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._transport._host} _discover failed status/body: "
                f"{status} {type(data)}"
            )

        response = data
        self.handle_response_error_code(response, "_discover failed")
        result = self._require_result_dict(
            response, f"{self._transport._host} _discover"
        )
        tpap = result.get("tpap")
        if not isinstance(tpap, dict):
            raise KasaException(
                f"{self._transport._host} _discover missing tpap object"
            )

        self._device_mac = str(result.get("mac") or "")
        self._tpap_tls = self._parse_optional_int(tpap.get("tls"))
        self._tpap_port = self._parse_optional_int(tpap.get("port"))
        self._tpap_dac = bool(tpap.get("dac"))
        self._tpap_pake = list(tpap.get("pake") or [])
        self._tpap_user_hash_type = self._parse_optional_int(tpap.get("user_hash_type"))

        self._transport._known_device_mac = self._device_mac
        self._transport._known_tpap_tls = self._tpap_tls
        self._transport._known_tpap_port = self._tpap_port
        self._transport._known_tpap_dac = self._tpap_dac
        self._transport._known_tpap_pake = list(self._tpap_pake)
        self._transport._known_tpap_user_hash_type = self._tpap_user_hash_type
        self._update_transport_url()

        # Discover runs before we know the real TLS mode, so rebuild for auth.
        self._transport._ssl_context = None

    async def _login(self, params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        body = {"method": "login", "params": params}
        status, data = await self._post_auth_request(body)
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"{self._transport._host} {step_name} bad status/body: "
                f"{status} {type(data)}"
            )

        response = data
        self.handle_response_error_code(response, f"TPAP {step_name} failed")
        return self._require_result_dict(
            response, f"{self._transport._host} {step_name}"
        )

    async def _post_auth_request(
        self, body: dict[str, Any]
    ) -> tuple[int, dict[str, Any] | bytes | None]:
        ssl_context = await self._transport.get_ssl_context()
        if self._tpap_tls == 2:
            (
                status,
                data,
                peer_cert_der,
            ) = await self._transport._http_client.post_with_info(
                self._transport._app_url.with_path("/"),
                json=body,
                headers=self._transport.COMMON_HEADERS,
                ssl=ssl_context,
            )
            self._transport._validate_peer_certificate(peer_cert_der)
            return status, data

        return await self._transport._http_client.post(
            self._transport._app_url.with_path("/"),
            json=body,
            headers=self._transport.COMMON_HEADERS,
            ssl=ssl_context,
        )

    def _update_transport_url(self) -> None:
        scheme = "https" if self._tpap_tls in (1, 2) else "http"
        if self._tpap_port and self._tpap_port > 0:
            port = self._tpap_port
        elif scheme == "https":
            port = self._transport.DEFAULT_HTTPS_PORT
        else:
            port = self._transport._port
        self._transport._app_url = URL.build(
            scheme=scheme,
            host=self._transport._host,
            port=port,
        )

    def handle_response_error_code(self, response: dict[str, Any], msg: str) -> None:
        """Translate device error codes to transport exceptions."""
        error_code_raw = response.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Device %s received unknown error code: %s",
                self._transport._host,
                error_code_raw,
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR

        if error_code is SmartErrorCode.SUCCESS:
            return

        full = f"{msg}: {self._transport._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(full, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self.reset()
            raise AuthenticationError(full, error_code=error_code)
        raise DeviceError(full, error_code=error_code)

    async def _perform_spake_handshake(self) -> None:
        candidate_secrets = self._iter_spake_candidate_secrets()
        last_error: KasaException | None = None

        if not candidate_secrets:
            raise AuthenticationError(
                f"TPAP: no SPAKE2+ credential candidates available for "
                f"{self._transport._host}"
            )

        for attempt, candidate_secret in enumerate(candidate_secrets, start=1):
            self._reset_spake_attempt_state()
            self._user_random = self._base64(os.urandom(32))
            register_params = {
                "sub_method": "pake_register",
                "username": self._get_auth_username(),
                "user_random": self._user_random,
                "cipher_suites": [1],
                "encryption": ["aes_128_ccm"],
                "passcode_type": self._get_passcode_type(),
                "stok": None,
            }

            try:
                register_result = await self._login(
                    register_params, step_name="pake_register"
                )
                credentials_string = self._resolve_spake_credentials(
                    register_result, candidate_secret
                )
                share_params = self._process_register_result(
                    register_result, credentials_string
                )
                if self._use_dac_certification():
                    self._dac_nonce_base64 = self._base64(os.urandom(16))
                    share_params["dac_nonce"] = self._dac_nonce_base64

                share_result = await self._login(share_params, step_name="pake_share")
                self._process_share_result(share_result)
                return
            except (_RetryableError, _ConnectionError):
                raise
            except KasaException as exc:
                last_error = exc
                if attempt < len(candidate_secrets):
                    _LOGGER.debug(
                        "TPAP: SPAKE2+ candidate %d/%d failed for %s: %s",
                        attempt,
                        len(candidate_secrets),
                        self._transport._host,
                        exc,
                    )

        if last_error is not None:
            if self._uses_smartcam_auth and 2 in self._tpap_pake:
                _LOGGER.debug(
                    (
                        "TPAP: all password-based SPAKE2+ smartcam candidates "
                        "failed for %s"
                    ),
                    self._transport._host,
                )
            raise last_error

        raise KasaException(  # pragma: no cover
            "TPAP: SPAKE2+ handshake did not produce a session"
        )

    @staticmethod
    def _md5_hex(value: str) -> str:
        return hashlib.md5(value.encode()).hexdigest()  # noqa: S324

    @staticmethod
    def _sha256_hex_upper(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest().upper()  # noqa: S324

    def _get_auth_username(self) -> str:
        username = "admin" if self._uses_smartcam_auth else self._transport._username
        username = username or "admin"
        if self._tpap_user_hash_type == 1:
            return self._sha256_hex_upper(username)
        return self._md5_hex(username)

    def _reset_spake_attempt_state(self) -> None:
        self._shared_key = None
        self._expected_dev_confirm = None
        self._dac_nonce_base64 = None
        self._user_random = None

    @staticmethod
    def _base64(value: bytes) -> str:
        return base64.b64encode(value).decode()

    @staticmethod
    def _unbase64(value: str) -> bytes:
        return base64.b64decode(value)

    @staticmethod
    def _sec1_to_xy(sec1: bytes, curve: ec.EllipticCurve) -> tuple[int, int]:
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(curve, sec1)
        numbers = public_key.public_numbers()
        return numbers.x, numbers.y

    @staticmethod
    def _xy_to_uncompressed(x: int, y: int, curve: ec.EllipticCurve) -> bytes:
        numbers = ec.EllipticCurvePublicNumbers(x, y, curve)
        public_key = numbers.public_key()
        return public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )

    @staticmethod
    def _len8le(value: bytes) -> bytes:
        return len(value).to_bytes(8, "little") + value

    @staticmethod
    def _encode_w(value: int) -> bytes:
        minimal_length = 1 if value == 0 else (value.bit_length() + 7) // 8
        unsigned = value.to_bytes(minimal_length, "big", signed=False)
        if minimal_length % 2 == 0:
            return unsigned
        if unsigned[0] & 0x80:
            return b"\x00" + unsigned
        return unsigned

    @staticmethod
    def _hash(algorithm: str, data: bytes) -> bytes:
        if algorithm.upper() == "SHA512":
            return hashlib.sha512(data).digest()
        return hashlib.sha256(data).digest()

    @staticmethod
    def _hkdf_expand(label: str, prk: bytes, digest_len: int, algorithm: str) -> bytes:
        hkdf_algorithm = (
            hashes.SHA512() if algorithm.upper() == "SHA512" else hashes.SHA256()
        )
        zero_salt = b"\x00" * digest_len
        return HKDF(
            algorithm=hkdf_algorithm,
            length=digest_len,
            salt=zero_salt,
            info=label.encode(),
        ).derive(prk)

    @staticmethod
    def _hmac(algorithm: str, key: bytes, data: bytes) -> bytes:
        digest = hashlib.sha512 if algorithm.upper() == "SHA512" else hashlib.sha256
        return hmac.new(key, data, digest).digest()

    @staticmethod
    def _cmac_aes(key: bytes, data: bytes) -> bytes:
        cmac = CMAC(algorithms.AES(key))
        cmac.update(data)
        return cmac.finalize()

    @staticmethod
    def _pbkdf2_sha256(
        password: bytes, salt: bytes, iterations: int, length: int
    ) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password, salt, iterations, length)

    @classmethod
    def _derive_ab(
        cls, credentials: bytes, salt: bytes, iterations: int, hash_len: int = 32
    ) -> tuple[int, int]:
        i_d = hash_len + 8
        derived = cls._pbkdf2_sha256(credentials, salt, iterations, 2 * i_d)
        return (
            int.from_bytes(derived[:i_d], "big"),
            int.from_bytes(derived[i_d:], "big"),
        )

    @staticmethod
    def _sha1_hex(value: str) -> str:
        return hashlib.sha1(value.encode()).hexdigest()  # noqa: S324

    @classmethod
    def _authkey_mask(cls, passcode: str, tmpkey: str, dictionary: str) -> str:
        masked = []
        max_length = max(len(tmpkey), len(passcode))
        for index in range(max_length):
            lhs = ord(passcode[index]) if index < len(passcode) else 0xBB
            rhs = ord(tmpkey[index]) if index < len(tmpkey) else 0xBB
            masked.append(dictionary[(lhs ^ rhs) % len(dictionary)])
        return "".join(masked)

    @classmethod
    def _sha1_username_mac_shadow(
        cls, username: str, mac12hex: str, password: str
    ) -> str:
        if (
            not username
            or len(mac12hex) != 12
            or not all(char in "0123456789abcdefABCDEF" for char in mac12hex)
        ):
            return password

        mac = ":".join(mac12hex[index : index + 2] for index in range(0, 12, 2)).upper()
        return cls._sha1_hex(cls._md5_hex(username) + "_" + mac)

    @classmethod
    def _md5_crypt(cls, password: str, prefix: str) -> str | None:
        if not prefix or not prefix.startswith("$1$") or len(password) > 30000:
            return None

        spec = prefix[3:]
        if "$" in spec:
            spec = spec.split("$", 1)[0]
        return md5_crypt.using(salt=spec[:8]).hash(password)

    @classmethod
    def _sha256_crypt(
        cls, password: str, prefix: str, rounds_from_params: int | None = None
    ) -> str | None:
        if not prefix:
            return None

        default_rounds = 5000
        min_rounds = 1000
        max_rounds = 999_999_999

        spec = prefix[3:] if prefix.startswith("$5$") else prefix
        rounds: int | None = None

        if spec.startswith("rounds="):
            rounds_part, _, salt_part = spec.partition("$")
            try:
                rounds = int(rounds_part.split("=", 1)[1])
            except ValueError:
                rounds = default_rounds
            rounds = max(min_rounds, min(max_rounds, rounds))
            salt = salt_part
        else:
            salt = spec.split("$", 1)[0] if "$" in spec else spec

        if rounds_from_params is not None:
            try:
                parsed_rounds = int(rounds_from_params)
            except (TypeError, ValueError):
                parsed_rounds = default_rounds
            rounds = max(min_rounds, min(max_rounds, parsed_rounds))

        salt = salt[:16]
        if rounds is not None:
            return sha256_crypt.using(rounds=rounds, salt=salt).hash(password)
        return sha256_crypt.using(salt=salt).hash(password)

    @classmethod
    def _build_credentials(
        cls, extra_crypt: dict | None, username: str, passcode: str, mac_no_colon: str
    ) -> str:
        if not extra_crypt:
            return f"{username}/{passcode}" if username else passcode

        crypt_type = (extra_crypt.get("type") or "").lower()
        params = extra_crypt.get("params")
        if not isinstance(params, dict):
            params = {}

        if crypt_type == "password_shadow":
            try:
                passwd_id = int(params.get("passwd_id", 0))
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "SPAKE2+: Invalid passwd_id provided, falling back to passcode"
                )
                return passcode
            prefix = str(params.get("passwd_prefix", "") or "")
            if passwd_id == 1:
                return cls._md5_crypt(passcode, prefix) or passcode
            if passwd_id == 2:
                return cls._sha1_hex(passcode)
            if passwd_id == 3:
                return cls._sha1_username_mac_shadow(username, mac_no_colon, passcode)
            if passwd_id == 5:
                return (
                    cls._sha256_crypt(
                        passcode,
                        prefix,
                        rounds_from_params=params.get("passwd_rounds"),
                    )
                    or passcode
                )
            return passcode

        if crypt_type == "password_authkey":
            tmpkey = str(params.get("authkey_tmpkey", "") or "")
            dictionary = str(params.get("authkey_dictionary", "") or "")
            if tmpkey and dictionary:
                return cls._authkey_mask(passcode, tmpkey, dictionary)
            return passcode

        if crypt_type == "password_sha_with_salt":
            try:
                sha_name = int(params.get("sha_name", -1))
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "SPAKE2+: Invalid sha_name provided, falling back to passcode"
                )
                return passcode
            sha_salt_b64 = str(params.get("sha_salt", "") or "")
            username_hint = "admin" if sha_name == 0 else "user"
            try:
                decoded_salt = base64.b64decode(sha_salt_b64).decode()
            except Exception:
                _LOGGER.debug(
                    "SPAKE2+: Invalid base64 salt provided, falling back to passcode"
                )
                return passcode
            return hashlib.sha256(
                (username_hint + decoded_salt + passcode).encode()
            ).hexdigest()

        return f"{username}/{passcode}" if username else passcode

    def _suite_hash_name(self, suite_type: int) -> str:
        return "SHA512" if suite_type in (2, 4, 5, 7, 9) else "SHA256"

    def _suite_mac_is_cmac(self, suite_type: int) -> bool:
        return suite_type in (8, 9)

    def _use_dac_certification(self) -> bool:
        return self._tpap_tls == 0 and self._tpap_dac

    @staticmethod
    def _mac_pass_from_device_mac(mac_colon: str) -> str:
        mac_hex = mac_colon.replace(":", "").replace("-", "")
        try:
            mac_bytes = bytes.fromhex(mac_hex)
        except ValueError as exc:
            raise KasaException(
                "Invalid device MAC for TPAP default passcode derivation"
            ) from exc
        if len(mac_bytes) < 6:
            raise KasaException(
                "Device MAC is too short for TPAP default passcode derivation"
            )
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

    def _get_passcode_type(self) -> str:
        if 0 in self._tpap_pake:
            return "default_userpw"
        if 2 in self._tpap_pake:
            return "userpw"
        if 1 in self._tpap_pake:
            return "userpw"
        if 3 in self._tpap_pake:
            return "shared_token"
        return "default_userpw"

    def _iter_spake_candidate_secrets(self) -> list[str]:
        if (not self._tpap_pake or 0 in self._tpap_pake) and self._device_mac:
            return [self._mac_pass_from_device_mac(self._device_mac)]

        creds = getattr(self._transport._config, "credentials", None)
        password = (creds.password if creds else "") or ""

        if not self._uses_smartcam_auth:
            return [password]

        candidates: list[str] = []
        if 2 in self._tpap_pake:
            candidates.extend(
                [
                    self._md5_hex(password),
                    self._sha256_hex_upper(password),
                ]
            )
        elif 1 in self._tpap_pake:
            candidates.append(password)
        elif 3 in self._tpap_pake:
            candidates.append(self._md5_hex(password))

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _resolve_spake_credentials(
        self, register_result: dict[str, Any], candidate_secret: str
    ) -> str:
        if (not self._tpap_pake or 0 in self._tpap_pake) and self._device_mac:
            return candidate_secret

        extra_crypt_value = register_result.get("extra_crypt")
        extra_crypt = extra_crypt_value if isinstance(extra_crypt_value, dict) else {}
        creds = getattr(self._transport._config, "credentials", None)
        username = (creds.username if creds else "") or ""
        mac_no_colon = self._device_mac.replace(":", "").replace("-", "")

        if self._uses_smartcam_auth:
            if not extra_crypt:
                return candidate_secret
            return self._build_credentials(
                extra_crypt, "", candidate_secret, mac_no_colon
            )

        return self._build_credentials(
            extra_crypt,
            username,
            candidate_secret,
            mac_no_colon,
        )

    @staticmethod
    def _suite_parameters(
        suite_type: int,
    ) -> tuple[bytes, bytes, Curve, ec.EllipticCurve]:
        if suite_type in (1, 2, 8, 9):
            return (
                bytes.fromhex(
                    "02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f"
                ),
                bytes.fromhex(
                    "03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49"
                ),
                NIST256p,
                ec.SECP256R1(),
            )
        if suite_type in (3, 4):
            return (
                bytes.fromhex(
                    "030ff0895ae5ebf6187080a82d82b42e2765e3b2f8749c7e05eba366434b363d3dc36f15314739074d2eb8613fceec2853"
                ),
                bytes.fromhex(
                    "02c72cf2e390853a1c1c4ad816a62fd15824f56078918f43f922ca21518f9c543bb252c5490214cf9aa3f0baab4b665c10"
                ),
                NIST384p,
                ec.SECP384R1(),
            )
        if suite_type == 5:
            return (
                bytes.fromhex(
                    "02003f06f38131b2ba2600791e82488e8d20ab889af753a41806c5db18d37d85608cfae06b82e4a72cd744c719193562a653ea1f119eef9356907edc9b56979962d7aa"
                ),
                bytes.fromhex(
                    "0200c7924b9ec017f3094562894336a53c50167ba8c5963876880542bc669e494b2532d76c5b53dfb349fdf69154b9e0048c58a42e8ed04cef052a3bc349d95575cd25"
                ),
                NIST521p,
                ec.SECP521R1(),
            )
        raise KasaException(f"Unsupported SPAKE2+ suite type: {suite_type}")

    def _process_register_result(
        self, register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        if self._user_random is None:
            raise KasaException("SPAKE2+ user random not initialized")

        context = "SPAKE2+ register response"
        dev_random = str(register_result.get("dev_random") or "")
        dev_salt = str(register_result.get("dev_salt") or "")
        dev_share = str(register_result.get("dev_share") or "")
        if not dev_random:
            raise KasaException(f"{context} missing dev_random")
        if not dev_salt:
            raise KasaException(f"{context} missing dev_salt")
        if not dev_share:
            raise KasaException(f"{context} missing dev_share")

        suite_type = self._require_int_field(
            register_result.get("cipher_suites"),
            field="cipher_suites",
            context=context,
        )
        iterations = self._require_int_field(
            register_result.get("iterations"),
            field="iterations",
            context=context,
        )
        if iterations <= 0:
            raise KasaException(f"{context} has invalid iterations")

        encryption = str(register_result.get("encryption") or "")
        if not encryption:
            raise KasaException(f"{context} missing encryption")
        chosen_cipher = self._normalize_cipher_id(encryption)
        if chosen_cipher not in self.CIPHER_PARAMETERS:
            raise KasaException(f"Unsupported TPAP session cipher: {encryption}")

        self._cipher_id = chosen_cipher
        self._hkdf_hash = self._suite_hash_name(suite_type)

        m_comp, n_comp, nist, crypto_curve = self._suite_parameters(suite_type)
        curve: CurveFp = nist.curve
        generator: PointJacobi = nist.generator
        order = generator.order()
        g_point = generator

        m_x, m_y = self._sec1_to_xy(m_comp, crypto_curve)
        n_x, n_y = self._sec1_to_xy(n_comp, crypto_curve)
        m_point = ellipticcurve.Point(curve, m_x, m_y, order)
        n_point = ellipticcurve.Point(curve, n_x, n_y, order)

        credential_bytes = credentials_string.encode()
        a_value, b_value = self._derive_ab(
            credential_bytes, self._unbase64(dev_salt), iterations, 32
        )
        w_value = a_value % order
        h_value = b_value % order
        x_value = secrets.randbelow(order - 1) + 1

        l_point = x_value * g_point + w_value * m_point
        l_encoded = self._xy_to_uncompressed(l_point.x(), l_point.y(), crypto_curve)

        device_share_bytes = self._unbase64(dev_share) if dev_share else b""
        r_x, r_y = self._sec1_to_xy(device_share_bytes, crypto_curve)
        r_point = ellipticcurve.Point(curve, r_x, r_y, order)
        r_encoded = self._xy_to_uncompressed(r_point.x(), r_point.y(), crypto_curve)

        r_prime = r_point + (-(w_value * n_point))
        z_point = x_value * r_prime
        v_point = (h_value % order) * r_prime

        z_encoded = self._xy_to_uncompressed(z_point.x(), z_point.y(), crypto_curve)
        v_encoded = self._xy_to_uncompressed(v_point.x(), v_point.y(), crypto_curve)
        m_encoded = self._xy_to_uncompressed(m_point.x(), m_point.y(), crypto_curve)
        n_encoded = self._xy_to_uncompressed(n_point.x(), n_point.y(), crypto_curve)

        context_hash = self._hash(
            self._hkdf_hash,
            self.PAKE_CONTEXT_TAG
            + self._unbase64(self._user_random)
            + self._unbase64(dev_random),
        )
        w_encoded = self._encode_w(w_value)

        transcript = (
            self._len8le(context_hash)
            + self._len8le(b"")
            + self._len8le(b"")
            + self._len8le(m_encoded)
            + self._len8le(n_encoded)
            + self._len8le(l_encoded)
            + self._len8le(r_encoded)
            + self._len8le(z_encoded)
            + self._len8le(v_encoded)
            + self._len8le(w_encoded)
        )

        transcript_hash = self._hash(self._hkdf_hash, transcript)
        digest_len = 64 if self._hkdf_hash.upper() == "SHA512" else 32
        mac_len = 16 if self._suite_mac_is_cmac(suite_type) else 32
        confirmation_keys = self._hkdf_expand(
            "ConfirmationKeys", transcript_hash, mac_len * 2, self._hkdf_hash
        )
        key_confirm_a = confirmation_keys[:mac_len]
        key_confirm_b = confirmation_keys[mac_len : mac_len * 2]
        self._shared_key = self._hkdf_expand(
            "SharedKey", transcript_hash, digest_len, self._hkdf_hash
        )

        if self._suite_mac_is_cmac(suite_type):
            user_confirm = self._cmac_aes(key_confirm_a, r_encoded)
            expected_dev_confirm = self._cmac_aes(key_confirm_b, l_encoded)
        else:
            user_confirm = self._hmac(self._hkdf_hash, key_confirm_a, r_encoded)
            expected_dev_confirm = self._hmac(self._hkdf_hash, key_confirm_b, l_encoded)

        self._expected_dev_confirm = self._base64(expected_dev_confirm)
        return {
            "sub_method": "pake_share",
            "user_share": self._base64(l_encoded),
            "user_confirm": self._base64(user_confirm),
        }

    def _verify_dac(self, share_result: dict[str, Any]) -> None:
        """Verify DAC certificate chain and proof signature."""
        try:
            dac_ca = str(share_result.get("dac_ca") or "")
            dac_ica = str(share_result.get("dac_ica") or "")
            dac_proof = share_result.get("dac_proof")
            if not (
                dac_ca and dac_proof and self._shared_key and self._dac_nonce_base64
            ):
                return
            if not isinstance(dac_proof, str):
                raise KasaException("Invalid DAC proof type")

            ca_cert = self._transport._load_certificate_value(dac_ca)
            ica_cert = (
                self._transport._load_certificate_value(dac_ica) if dac_ica else None
            )
            self._transport._verify_dac_certificate_chain(ca_cert, ica_cert)
            message = self._shared_key + self._unbase64(self._dac_nonce_base64)
            signature = self._unbase64(dac_proof)
            public_key = ca_cert.public_key()
            if not isinstance(public_key, ec.EllipticCurvePublicKey):
                raise KasaException(
                    "Unsupported DAC proof public key type: "
                    f"{type(public_key).__name__}"
                )
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            _LOGGER.error("SPAKE2+: Invalid DAC proof signature")
            raise KasaException("Invalid DAC proof signature") from exc
        except Exception as exc:
            _LOGGER.error("SPAKE2+: DAC verification failed: %s", exc)
            raise KasaException(f"DAC verification failed: {exc}") from exc

    def _process_share_result(self, share_result: dict[str, Any]) -> None:
        dev_confirm = str(share_result.get("dev_confirm") or "").lower()
        if not dev_confirm:
            raise KasaException("SPAKE2+ share response missing dev_confirm")
        if dev_confirm != (self._expected_dev_confirm or "").lower():
            raise KasaException("SPAKE2+ confirmation mismatch")

        if self._use_dac_certification():
            self._verify_dac(share_result)

        session_id = str(
            share_result.get("sessionId") or share_result.get("stok") or ""
        )
        if not session_id:
            _LOGGER.error("SPAKE2+: Missing session ID from device")
            raise KasaException("Missing session fields from device")
        if self._shared_key is None:
            raise KasaException("SPAKE2+ shared key was not derived")
        start_seq = share_result.get("start_seq")
        if start_seq is None:
            raise KasaException("Missing session fields from device")
        try:
            sequence = int(start_seq)
        except (TypeError, ValueError) as exc:
            raise KasaException("Invalid session fields from device") from exc

        self._key, self._base_nonce = self.key_nonce_from_shared(
            self._shared_key, self._cipher_id, hkdf_hash=self._hkdf_hash
        )
        self._session_id = session_id
        self._sequence = sequence
        self._ds_url = URL(f"{self._transport._app_url}/stok={self._session_id}/ds")

    @classmethod
    def _normalize_cipher_id(cls, cipher_id: str) -> str:
        return cipher_id.lower().replace("-", "_")

    @classmethod
    def _cipher_parameters(
        cls, cipher_id: str
    ) -> tuple[bytes, bytes, bytes, bytes, int]:
        normalized = cls._normalize_cipher_id(cipher_id)
        try:
            return cls.CIPHER_PARAMETERS[normalized]
        except KeyError as exc:
            raise KasaException(
                f"Unsupported TPAP session cipher: {cipher_id}"
            ) from exc

    @staticmethod
    def _hkdf(
        master: bytes, *, salt: bytes, info: bytes, length: int, algo: str = "SHA256"
    ) -> bytes:
        algorithm = hashes.SHA256() if algo.upper() == "SHA256" else hashes.SHA512()
        return HKDF(algorithm=algorithm, length=length, salt=salt, info=info).derive(
            master
        )

    @staticmethod
    def _nonce_from_base(base_nonce: bytes, seq: int) -> bytes:
        if len(base_nonce) < 4:
            raise ValueError("base nonce too short")
        return base_nonce[:-4] + struct.pack(">I", seq)

    @classmethod
    def key_nonce_from_shared(
        cls, shared_key: bytes, cipher_id: str, hkdf_hash: str = "SHA256"
    ) -> tuple[bytes, bytes]:
        """Derive the session key and base nonce from the shared key."""
        key_salt, key_info, nonce_salt, nonce_info, key_len = cls._cipher_parameters(
            cipher_id
        )
        return (
            cls._hkdf(
                shared_key,
                salt=key_salt,
                info=key_info,
                length=key_len,
                algo=hkdf_hash,
            ),
            cls._hkdf(
                shared_key,
                salt=nonce_salt,
                info=nonce_info,
                length=cls.NONCE_LEN,
                algo=hkdf_hash,
            ),
        )

    @classmethod
    def _encrypt_payload(
        cls, cipher_id: str, key: bytes, base_nonce: bytes, plaintext: bytes, seq: int
    ) -> bytes:
        nonce = cls._nonce_from_base(base_nonce, seq)
        normalized = cls._normalize_cipher_id(cipher_id)
        if normalized.startswith("aes_"):
            return AESCCM(key, tag_length=cls.TAG_LEN).encrypt(nonce, plaintext, None)
        return ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)

    @classmethod
    def _decrypt_payload(
        cls,
        cipher_id: str,
        key: bytes,
        base_nonce: bytes,
        ciphertext_and_tag: bytes,
        seq: int,
    ) -> bytes:
        nonce = cls._nonce_from_base(base_nonce, seq)
        normalized = cls._normalize_cipher_id(cipher_id)
        if normalized.startswith("aes_"):
            return AESCCM(key, tag_length=cls.TAG_LEN).decrypt(
                nonce, ciphertext_and_tag, None
            )
        return ChaCha20Poly1305(key).decrypt(nonce, ciphertext_and_tag, None)

    @classmethod
    def sec_encrypt(
        cls,
        cipher_id: str,
        key: bytes,
        base_nonce: bytes,
        plaintext: bytes,
        seq: int = 1,
    ) -> tuple[bytes, bytes]:
        """Encrypt plaintext into a `(ciphertext, tag)` pair."""
        combined = cls._encrypt_payload(cipher_id, key, base_nonce, plaintext, seq)
        return combined[: -cls.TAG_LEN], combined[-cls.TAG_LEN :]

    @classmethod
    def sec_decrypt(
        cls,
        cipher_id: str,
        key: bytes,
        base_nonce: bytes,
        ciphertext: bytes,
        tag: bytes,
        seq: int = 1,
    ) -> bytes:
        """Decrypt a `(ciphertext, tag)` pair."""
        return cls._decrypt_payload(cipher_id, key, base_nonce, ciphertext + tag, seq)

    def _ensure_established(self) -> tuple[str, int, URL, bytes, bytes]:
        if not self.is_established:
            raise KasaException("TPAP transport is not established")
        if TYPE_CHECKING:
            assert self._sequence is not None
            assert self._ds_url is not None
            assert self._key is not None
            assert self._base_nonce is not None

        return (
            self._cipher_id,
            self._sequence,
            self._ds_url,
            self._key,
            self._base_nonce,
        )

    def encrypt(self, payload: bytes | str) -> tuple[bytes, int]:
        """Encrypt a DS request body using the current sequence number."""
        cipher_id, seq, _, key, base_nonce = self._ensure_established()
        plaintext = payload.encode() if isinstance(payload, str) else payload
        encrypted = self._encrypt_payload(cipher_id, key, base_nonce, plaintext, seq)
        self._sequence = seq + 1
        return struct.pack(">I", seq) + encrypted, seq

    def advance(self, seq: int) -> None:
        """Advance the request sequence after a successful POST."""
        if self._sequence == seq:
            self._sequence = seq + 1

    def decrypt(self, payload: bytes, request_seq: int) -> bytes:
        """Decrypt a DS response body."""
        cipher_id, _, _, key, base_nonce = self._ensure_established()
        if len(payload) < 4 + self.TAG_LEN:
            raise KasaException("TPAP response too short")

        response_seq = struct.unpack(">I", payload[:4])[0]
        if response_seq != request_seq:
            _LOGGER.debug(
                "Device returned unexpected rseq %d (expected %d)",
                response_seq,
                request_seq,
            )
        return self._decrypt_payload(
            cipher_id, key, base_nonce, payload[4:], response_seq
        )


class TpapTransport(BaseTransport):
    """Transport implementing the TPAP encrypted DS channel."""

    USE_SMARTCAM_AUTH = False
    DEFAULT_PORT: int = 80
    DEFAULT_HTTPS_PORT: int = 4433
    CIPHERS = ":".join(
        [
            "ECDHE-ECDSA-AES256-GCM-SHA384",
            "ECDHE-ECDSA-AES256-SHA384",
            "ECDHE-ECDSA-AES256-SHA",
            "ECDHE-ECDSA-AES128-GCM-SHA256",
            "ECDHE-ECDSA-AES128-SHA256",
            "ECDHE-ECDSA-AES128-SHA",
            "ECDHE-RSA-AES256-GCM-SHA384",
            "ECDHE-RSA-AES256-SHA384",
            "ECDHE-RSA-AES256-SHA",
            "ECDHE-RSA-AES128-GCM-SHA256",
            "ECDHE-RSA-AES128-SHA256",
            "ECDHE-RSA-AES128-SHA",
        ]
    )
    COMMON_HEADERS = {"Content-Type": "application/json"}
    TPAP_ROOT_CA_PEM = """
-----BEGIN CERTIFICATE-----
MIICNzCCAdygAwIBAgIUNLD7w5j5WU/efCe8bqkfGSRGgLYwCgYIKoZIzj0EAwIw
ezEnMCUGA1UEAwweVFAtTElOSyBTWVNURU1TIERFVklDRSBST09UIENBMR0wGwYD
VQQKDBRUUC1MSU5LIFNZU1RFTVMgSU5DLjEPMA0GA1UEBwwGSXJ2aW5lMRMwEQYD
VQQIDApDYWxpZm9ybmlhMQswCQYDVQQGEwJVUzAgFw0yNDExMjIwMjU3NDhaGA8y
MDU0MTExNTAyNTc0OFowezEnMCUGA1UEAwweVFAtTElOSyBTWVNURU1TIERFVklD
RSBST09UIENBMR0wGwYDVQQKDBRUUC1MSU5LIFNZU1RFTVMgSU5DLjEPMA0GA1UE
BwwGSXJ2aW5lMRMwEQYDVQQIDApDYWxpZm9ybmlhMQswCQYDVQQGEwJVUzBZMBMG
ByqGSM49AgEGCCqGSM49AwEHA0IABLwo8H9H6BoJDvcoewi4wPrPryVXir4z4yXV
n29R5XCAcFfKk06pYPupG6pjaKOLKWXnaOdPZThDFxwGLo3urV2jPDA6MAsGA1Ud
DwQEAwIBhjAMBgNVHRMEBTADAQH/MB0GA1UdDgQWBBRivfUtiHYsZBOKo80uZEwk
XhBkdDAKBggqhkjOPQQDAgNJADBGAiEA+7j5jemtXcGYN0unH+9rjVhVAL7WrsOi
5rbc0IIvD6MCIQCZuGGssu4Ygt2V8Vr0QF2fO9wxfNB3aRRMYQ+6lMrLGA==
-----END CERTIFICATE-----
""".strip()
    TPAP_DEVICE_MAC_OID = x509.ObjectIdentifier("1.0.15961.13.375")

    def __init__(self, *, config: DeviceConfig) -> None:
        """Initialize HTTP client and state."""
        super().__init__(config=config)
        self._http_client: HttpClient = HttpClient(self._config)
        self._username: str = (
            self._config.credentials.username if self._config.credentials else ""
        ) or ""
        self._password: str = (
            self._config.credentials.password if self._config.credentials else ""
        ) or ""
        self._ssl_context: ssl.SSLContext | bool | None = None
        self._state = TransportState.NOT_ESTABLISHED
        protocol = "https" if config.connection_type.https else "http"
        self._bootstrap_url = URL(f"{protocol}://{self._host}:{self._port}")
        self._app_url = self._bootstrap_url
        self._known_device_mac = ""
        self._known_tpap_tls: int | None = None
        self._known_tpap_port: int | None = None
        self._known_tpap_dac = False
        self._known_tpap_pake: list[int] = []
        self._known_tpap_user_hash_type: int | None = None
        self._send_lock: asyncio.Lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()
        self._encryption_session = self._create_encryption_session()

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        config = self._config
        if port := config.connection_type.http_port:
            return port
        if config.connection_type.https:
            return self.DEFAULT_HTTPS_PORT
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """Return a stable hash of credentials if available, else None."""
        return self._config.credentials_hash

    def _create_encryption_session(self) -> TpapEncryptionSession:
        return TpapEncryptionSession(self)

    def _get_initial_app_url(self) -> URL:
        if self._known_tpap_port and self._known_tpap_port > 0:
            known_port = self._known_tpap_port
        elif self._known_tpap_tls in (1, 2):
            known_port = self.DEFAULT_HTTPS_PORT
        else:
            return self._bootstrap_url

        known_scheme = "https" if self._known_tpap_tls in (1, 2) else "http"
        return URL.build(
            scheme=known_scheme,
            host=self._host,
            port=known_port,
        )

    @classmethod
    def _load_root_ca_certificate(cls) -> x509.Certificate:
        return x509.load_pem_x509_certificate(cls.TPAP_ROOT_CA_PEM.encode())

    @classmethod
    def _load_certificate_value(cls, certificate_value: str) -> x509.Certificate:
        raw_value = certificate_value.strip()
        if not raw_value:
            raise KasaException("Empty certificate value")

        candidates: list[bytes] = [raw_value.encode()]
        decoded_candidate: bytes | None = None
        try:
            decoded_candidate = base64.b64decode(raw_value, validate=True)
        except Exception:
            decoded_candidate = None
        if decoded_candidate is not None:
            candidates.insert(0, decoded_candidate)

        last_error: Exception | None = None
        for candidate in candidates:
            try:
                if b"-----BEGIN CERTIFICATE-----" in candidate:
                    return x509.load_pem_x509_certificate(candidate)
                return x509.load_der_x509_certificate(candidate)
            except Exception as exc:
                last_error = exc

        raise KasaException("Invalid certificate value") from last_error

    @staticmethod
    def _verify_certificate_validity(certificate: x509.Certificate) -> None:
        now = datetime.now(UTC)
        if hasattr(certificate, "not_valid_before_utc"):
            not_before = certificate.not_valid_before_utc
            not_after = certificate.not_valid_after_utc
        else:
            not_before = certificate.not_valid_before.replace(tzinfo=UTC)
            not_after = certificate.not_valid_after.replace(tzinfo=UTC)
        if now < not_before or now > not_after:
            raise KasaException("Certificate is outside its validity period")

    @staticmethod
    def _verify_certificate_signature(
        certificate: x509.Certificate, issuer: x509.Certificate
    ) -> None:
        public_key = issuer.public_key()
        signature_hash = certificate.signature_hash_algorithm
        if signature_hash is None:
            raise KasaException("Certificate signature hash algorithm is unavailable")
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                ec.ECDSA(signature_hash),
            )
            return
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                padding.PKCS1v15(),
                signature_hash,
            )
            return
        raise KasaException(
            f"Unsupported DAC issuer public key type: {type(public_key).__name__}"
        )

    @classmethod
    def _verify_dac_certificate_chain(
        cls,
        dac_ca_certificate: x509.Certificate,
        dac_ica_certificate: x509.Certificate | None,
    ) -> None:
        try:
            root_certificate = cls._load_root_ca_certificate()
            cls._verify_certificate_validity(dac_ca_certificate)
            if dac_ica_certificate is not None:
                cls._verify_certificate_validity(dac_ica_certificate)
                cls._verify_certificate_signature(
                    dac_ca_certificate, dac_ica_certificate
                )
                cls._verify_certificate_signature(dac_ica_certificate, root_certificate)
            else:
                cls._verify_certificate_signature(dac_ca_certificate, root_certificate)
        except Exception as exc:
            raise KasaException(
                f"DAC certificate chain verification failed: {exc}"
            ) from exc

    @staticmethod
    def _decode_der_length(value: bytes, index: int) -> tuple[int, int]:
        if index >= len(value):
            raise ValueError("Missing DER length")
        first = value[index]
        if first & 0x80 == 0:
            return first, index + 1
        num_octets = first & 0x7F
        if num_octets == 0 or index + 1 + num_octets > len(value):
            raise ValueError("Invalid DER length")
        length = int.from_bytes(value[index + 1 : index + 1 + num_octets], "big")
        return length, index + 1 + num_octets

    @classmethod
    def _decode_othername_value(cls, value: bytes) -> str | None:
        if not value:
            return None

        try:
            tag = value[0]
            length, payload_index = cls._decode_der_length(value, 1)
            payload = value[payload_index : payload_index + length]
        except ValueError:
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return None

        if tag in (0x0C, 0x13, 0x16):
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if tag == 0x1E:
            try:
                return payload.decode("utf-16-be")
            except UnicodeDecodeError:
                return None
        if tag == 0x04 or (tag & 0xE0) == 0xA0:
            return cls._decode_othername_value(payload)
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return None

    @classmethod
    def _extract_tpap_mac_values(cls, certificate: x509.Certificate) -> list[str]:
        try:
            subject_alt_name = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
        except x509.ExtensionNotFound:
            return []

        values: list[str] = []
        for general_name in subject_alt_name:
            if (
                isinstance(general_name, x509.OtherName)
                and general_name.type_id == cls.TPAP_DEVICE_MAC_OID
                and (decoded := cls._decode_othername_value(general_name.value))
            ):
                values.append(decoded)
        return values

    @staticmethod
    def _normalize_mac(value: str) -> str:
        return "".join(char for char in value if char.isalnum()).upper()

    def _validate_peer_certificate(self, peer_cert_der: bytes | None) -> None:
        if self._encryption_session.tls_mode != 2:
            return
        if not peer_cert_der:
            raise KasaException("Missing peer certificate for TPAP TLS verification")

        device_mac = self._encryption_session.device_mac
        if not device_mac:
            raise KasaException("Missing device MAC for TPAP TLS verification")

        certificate = x509.load_der_x509_certificate(peer_cert_der)
        normalized_device_mac = self._normalize_mac(device_mac)
        for certificate_mac in self._extract_tpap_mac_values(certificate):
            if normalized_device_mac in self._normalize_mac(certificate_mac):
                return

        raise KasaException("Device MAC address does not match TPAP certificate")

    @staticmethod
    def _require_response_dict(
        response_data: dict[str, Any] | bytes | None, *, context: str
    ) -> dict[str, Any]:
        if not isinstance(response_data, dict):
            raise KasaException(f"Unexpected {context} response body type from device")
        response_dict: dict[str, Any] = response_data
        return response_dict

    @staticmethod
    def _load_json_dict(payload: bytes, *, context: str) -> dict[str, Any]:
        response_data = json_loads(payload.decode())
        if not isinstance(response_data, dict):
            raise KasaException(f"Unexpected {context} JSON response body type")
        response_dict: dict[str, Any] = response_data
        return response_dict

    @staticmethod
    def _should_retry_live_session(exc: Exception) -> bool:
        if isinstance(exc, _ConnectionError):
            return "Connection reset" in str(exc)

        if not isinstance(exc, _RetryableError):
            return False

        return exc.error_code in {
            SmartErrorCode.SESSION_TIMEOUT_ERROR,
            SmartErrorCode.SESSION_EXPIRED,
            SmartErrorCode.INVALID_NONCE,
            SmartErrorCode.TRANSPORT_NOT_AVAILABLE_ERROR,
        }

    async def get_ssl_context(self) -> ssl.SSLContext | bool:
        """Get or create SSL context as configured by device (TLS mode)."""
        if self._ssl_context is None:
            self._ssl_context = await self._loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    def _create_ssl_context(self) -> ssl.SSLContext | bool:
        tls_mode = self._encryption_session.tls_mode
        if tls_mode == 0:
            return False

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False

        if tls_mode in (None, 1):
            context.verify_mode = ssl.CERT_NONE
            return context

        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=self.TPAP_ROOT_CA_PEM)
        return context

    async def send(self, request: str) -> dict[str, Any]:
        """Send an encrypted DS request and return parsed JSON response."""
        for attempt in range(2):
            try:
                return await self._send_once(request)
            except Exception as exc:
                if attempt == 0 and self._should_retry_live_session(exc):
                    _LOGGER.debug(
                        "TPAP: resetting live session and retrying after error: %s",
                        exc,
                    )
                    await self.reset()
                    continue
                raise

        raise KasaException("TPAP request retry exhausted")  # pragma: no cover

    async def _send_once(self, request: str) -> dict[str, Any]:
        """Send a single encrypted DS request."""
        if (
            self._state is TransportState.NOT_ESTABLISHED
            or not self._encryption_session.is_established
        ):
            await self._encryption_session.perform_handshake()

        ds_url = self._encryption_session.ds_url
        if ds_url is None:
            raise KasaException("TPAP transport is not established")

        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        async with self._send_lock:
            payload, seq = self._encryption_session.encrypt(request)
            headers = {"Content-Type": "application/octet-stream"}
            status, data = await self._post_secure_request(
                ds_url, payload=payload, headers=headers
            )
            if status != 200:
                raise KasaException(
                    f"{self._host} responded with unexpected status {status} "
                    "on secure request"
                )

        if isinstance(data, bytes | bytearray):
            plaintext = self._encryption_session.decrypt(bytes(data), seq)
            return self._load_json_dict(plaintext, context="TPAP secure")

        if isinstance(data, dict):
            self._encryption_session.handle_response_error_code(
                data, "Error sending TPAP request"
            )
            return self._require_response_dict(data, context="TPAP secure")

        raise KasaException("Unexpected response body type from device")

    async def _post_secure_request(
        self,
        ds_url: URL,
        *,
        payload: bytes,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, Any] | bytes | None]:
        ssl_context = await self.get_ssl_context()
        if self._encryption_session.tls_mode == 2:
            status, data, peer_cert_der = await self._http_client.post_with_info(
                ds_url,
                data=payload,
                headers=headers,
                ssl=ssl_context,
            )
            self._validate_peer_certificate(peer_cert_der)
            return status, data

        return await self._http_client.post(
            ds_url,
            data=payload,
            headers=headers,
            ssl=ssl_context,
        )

    async def close(self) -> None:
        """Close underlying HTTP client and clear state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset transport state; session will be re-established on demand."""
        self._encryption_session.reset()


class TpapSmartCamTransport(TpapTransport):
    """TPAP transport variant for SmartCamProtocol devices."""

    USE_SMARTCAM_AUTH = True
