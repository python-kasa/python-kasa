"""Implementation of the TP-Link TPAP transport.

TPAP is the login newer Tapo and Kasa firmware uses instead of KLAP or AES:
a SPAKE2+ exchange that gives a shared key, then an encrypted session.

The login values are the TLS mode (0 for http, 1 for TLS, 2 for TLS checked
against TP-Link's device root CA), the port, the passcode types the device
accepts (``pake``), whether it proves itself with its attestation certificate
(``dac``) and its MAC. They come from the ``tpap`` object of the UDP discovery
reply. Without it the client asks the device with an in-band ``discover``,
except cameras, which refuse that and get fixed defaults.

pake_register: the client sends a random value and the passcode type. The
device answers with its own random value, a salt, an iteration count, its
SPAKE2+ share and, in ``extra_crypt``, how the password has to be encoded.

pake_share: both sides derive w0 and w1 from the encoded password with
PBKDF2-HMAC-SHA256. The client sends its share and confirmation, and the
device answers with its own confirmation, which the client checks, a session
id (``stok``) and a start sequence number. With ``dac`` the device also signs
the shared key and a nonce from the client with its attestation certificate.
A rejected pake_share counts toward the device's lockout, so it is never
retried.

encryption: the session key and nonce come from the shared key with
HKDF-SHA256. Requests go to ``/stok=<stok>/ds``, encrypted with AES-CCM or
ChaCha20-Poly1305 and prefixed with their sequence number, which also goes
into the nonce and increments with every request.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import secrets
import ssl
import struct
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM, ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from yarl import URL

from kasa.credentials import Credentials
from kasa.deviceconfig import DeviceConfig, DeviceFamily
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
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads

from .basetransport import BaseTransport
from .sslcontext import get_ssl_context
from .tpap import cert, crypto

_LOGGER = logging.getLogger(__name__)


class TpapTransport(BaseTransport):
    """Implementation of the TPAP encryption protocol."""

    DEFAULT_PORT: int = 80
    # Errors on a /ds request that mean the device dropped the session, so the
    # protocol logs in again and resends: -2402 (invalid argument, also what
    # -40420 and -40421 in an HTTP error body become) and -2101 (auth attempts
    # limit).
    SESSION_LOST_ERROR_CODES = frozenset({-2402, -2101, -40420, -40421})
    DEFAULT_HTTPS_PORT: int = 4433
    DEFAULT_CAMERA_HTTPS_PORT: int = 443
    CAMERA_AUTH_DEVICE_FAMILIES = (
        DeviceFamily.SmartIpCamera,
        DeviceFamily.SmartTapoDoorbell,
    )
    ROBOT_TPAP_DEVICE_FAMILIES = {DeviceFamily.SmartTapoRobovac}
    # Kasa IOT devices follow other login rules than Tapo devices
    KASA_IOT_DEVICE_FAMILIES = {
        DeviceFamily.IotSmartPlugSwitch,
        DeviceFamily.IotSmartBulb,
    }
    COMMON_HEADERS = {"Content-Type": "application/json"}
    # PBKDF2-HMAC-SHA256 iteration count from an unauthenticated pake_register
    # response is otherwise unbounded and runs synchronously on the event loop;
    # cap it well above any realistic device value to prevent a pre-auth DoS.
    MAX_PAKE_ITERATIONS = 100_000
    # The iteration count when pake_register leaves it out.
    DEFAULT_PAKE_ITERATIONS = 10_000

    def __init__(self, *, config: DeviceConfig) -> None:
        """Create the transport."""
        super().__init__(config=config)
        if self._credentials is None and self._credentials_hash:
            # BaseTransport kept the hash only if it has this transport's shape
            self._credentials = Credentials._from_plaintext_hash(self._credentials_hash)
            self._config.credentials = self._credentials
        self._http_client: HttpClient = HttpClient(self._config)
        self._ssl_context: ssl.SSLContext | bool | None = None
        protocol = "https" if config.connection_type.https else "http"
        self._bootstrap_url = URL(f"{protocol}://{self._host}:{self._port}")
        self._app_url = self._bootstrap_url
        # The login values: from discovery, else the in-band discover or
        # the camera defaults
        self._device_mac = ""
        self._tpap_tls: int | None = None
        self._tpap_port: int | None = None
        self._tpap_dac = False
        self._tpap_pake: list[int] | None = None
        self._tpap_user_hash_type: int | None = None
        self._has_discovery_tpap = False
        if (tpap := config.connection_type.tpap) is not None:
            self._has_discovery_tpap = True
            self._device_mac = tpap.mac or ""
            self._tpap_tls = tpap.tls
            self._tpap_port = tpap.port
            self._tpap_dac = tpap.dac
            self._tpap_pake = None if tpap.pake is None else list(tpap.pake)
            self._tpap_user_hash_type = tpap.user_hash_type
        self._handshake_lock = asyncio.Lock()
        self._send_lock: asyncio.Lock = asyncio.Lock()
        # The login state, and the session once logged in
        self._encryption_session: TpapEncryptionSession | None = None
        self._ds_url: URL | None = None
        self._cipher_id = "aes_128_ccm"
        self._shared_key: bytes | None = None
        self._expected_dev_confirm: str | None = None
        self._dac_nonce_base64: str | None = None
        self._user_random: str | None = None
        self._reset_state()
        _LOGGER.debug("Created TPAP transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        config = self._config
        if port := config.connection_type.http_port:
            return port
        if config.connection_type.https:
            if config.connection_type.device_family in self.CAMERA_AUTH_DEVICE_FAMILIES:
                return self.DEFAULT_CAMERA_HTTPS_PORT
            return self.DEFAULT_HTTPS_PORT
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""
        if self._credentials and self._credentials.username:
            credentials_hash = {
                "un": self._credentials.username,
                "pwd": self._credentials.password,
            }
            return base64.b64encode(json_dumps(credentials_hash).encode()).decode()
        return self._credentials_hash

    @classmethod
    def is_transport_credentials_hash(cls, credentials_hash: str) -> bool:
        """Whether the hash has the shape this transport produces."""
        return Credentials._from_plaintext_hash(credentials_hash) is not None

    @property
    def _uses_camera_auth(self) -> bool:
        device_family = self._config.connection_type.device_family
        return device_family in self.CAMERA_AUTH_DEVICE_FAMILIES

    @property
    def _uses_robot_tpap_auth(self) -> bool:
        device_family = self._config.connection_type.device_family
        return device_family in self.ROBOT_TPAP_DEVICE_FAMILIES

    @property
    def _uses_kasa_iot_auth(self) -> bool:
        device_family = self._config.connection_type.device_family
        return device_family in self.KASA_IOT_DEVICE_FAMILIES

    def _build_app_url(self, *, tls_mode: int | None, port: int | None) -> URL:
        family = self._config.connection_type.device_family
        if family in self.KASA_IOT_DEVICE_FAMILIES:
            # Kasa devices: https for any tls but 0, and the tpap port or
            # else 80, whatever the scheme
            scheme = "https" if tls_mode else "http"
            resolved_port = (
                port
                if port and port > 0
                else self._config.port_override or self.DEFAULT_PORT
            )
            return URL.build(scheme=scheme, host=self._host, port=resolved_port)
        # Cameras are always https, on their own port
        is_camera = family in self.CAMERA_AUTH_DEVICE_FAMILIES
        scheme = "https" if is_camera or tls_mode in (1, 2) else "http"
        if port and port > 0:
            resolved_port = port
        elif scheme == "http" or is_camera:
            resolved_port = self._port
        else:
            resolved_port = self.DEFAULT_HTTPS_PORT
        return URL.build(
            scheme=scheme,
            host=self._host,
            port=resolved_port,
        )

    def _get_initial_app_url(self) -> URL:
        if not (self._tpap_port and self._tpap_port > 0) and (
            self._tpap_tls not in (1, 2)
        ):
            return self._bootstrap_url

        return self._build_app_url(
            tls_mode=self._tpap_tls,
            port=self._tpap_port,
        )

    def _update_app_url(self) -> None:
        self._app_url = self._build_app_url(
            tls_mode=self._tpap_tls,
            port=self._tpap_port,
        )

    async def get_ssl_context(self) -> ssl.SSLContext | bool:
        """Get or create the SSL context for the device's TLS mode."""
        if self._ssl_context is None:
            tls_mode = self._tpap_tls
            if tls_mode == 0:
                self._ssl_context = False
            elif tls_mode == 2:
                loop = asyncio.get_running_loop()
                self._ssl_context = await loop.run_in_executor(
                    None, self._create_tls2_ssl_context
                )
            else:
                # Unverified TLS, shared with the other https transports
                self._ssl_context = await get_ssl_context()
        return self._ssl_context

    def _create_tls2_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=cert.TPAP_ROOT_CA_PEM)
        # ECDSA suites only, and the certificate has to name the device MAC
        context.set_ciphers(cert.TLS2_CIPHERS)
        if mac := self._device_mac:
            context.sslobject_class = cert.mac_checking_sslobject(mac)
        else:
            _LOGGER.debug(
                "No device MAC to check the TLS certificate of %s against",
                self._host,
            )
        return context

    async def perform_handshake(self) -> None:
        """Perform the handshake."""
        async with self._handshake_lock:
            if self._encryption_session is not None:
                return

            self._reset_state()
            _LOGGER.debug("Starting handshake with %s", self._host)

            if self._has_discovery_tpap:
                # Log in with what UDP discovery announced
                self._update_app_url()
                source = "discovery"
            elif self._uses_camera_auth:
                # Cameras refuse the in-band discover (-40209)
                self._apply_default_params()
                source = "the camera defaults"
            else:
                await self._discover()
                source = "the in-band discover"
            _LOGGER.debug(
                "Using the TPAP login from %s for %s: tls %s, port %s, pake %s, "
                "dac %s, url %s",
                source,
                self._host,
                self._tpap_tls,
                self._tpap_port,
                self._tpap_pake,
                self._tpap_dac,
                self._app_url,
            )
            await self.perform_login()

            _LOGGER.debug("Handshake with %s complete", self._host)

    async def _discover(self) -> None:
        body = {"method": "login", "params": {"sub_method": "discover"}}
        status, data = await self._http_client.post(
            self._app_url.with_path("/"),
            json=body,
            headers=self.COMMON_HEADERS,
            ssl=await self.get_ssl_context(),
        )
        _LOGGER.debug(
            "Discover posted at %s. Host is %s, Response status is %s",
            datetime.now(),
            self._host,
            status,
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"TPAP discover failed for {self._host}: {status} {type(data)}"
            )

        self._handle_login_error_code(data, "discover")
        result = self._require_result_dict(data)
        tpap = result.get("tpap")
        if not isinstance(tpap, dict):
            raise KasaException("TPAP discover response missing tpap object")

        self._device_mac = str(result.get("mac") or "")
        self._tpap_tls = self._parse_optional_int(tpap.get("tls"))
        # Some devices (RV50 Pro Omni) answer the in-band discover over TLS
        # with tls=0.  A session bootstrapped over https stays on CA-verified
        # TLS (mode 2) rather than falling back to plaintext on a TLS port.
        if self._tpap_tls == 0 and self._app_url.scheme == "https":
            self._tpap_tls = 2
        self._tpap_port = self._parse_optional_int(tpap.get("port"))
        self._tpap_dac = bool(tpap.get("dac"))
        pake = tpap.get("pake")
        self._tpap_pake = list(pake) if isinstance(pake, list) else None
        self._tpap_user_hash_type = self._parse_optional_int(tpap.get("user_hash_type"))

        self._update_app_url()

        # Discover runs before we know the real TLS mode, so rebuild for auth.
        self._ssl_context = None

    def _apply_default_params(self) -> None:
        """Set up a camera login without the in-band discover.

        Password login, no DAC attestation, and TLS when the connection is
        https. That matches what the C101 and C510W cameras announce in UDP
        discovery (``tpap: {pake: [2], tls: 1, port: 443}``).
        """
        self._tpap_tls = 1 if self._config.connection_type.https else 0
        self._tpap_port = self._port
        self._tpap_dac = False
        self._tpap_pake = [2]
        self._tpap_user_hash_type = None
        self._update_app_url()
        self._ssl_context = None

    async def _login(self, params: dict[str, Any], *, step_name: str) -> dict[str, Any]:
        body = {"method": "login", "params": params}
        ssl_context = await self.get_ssl_context()
        status, data = await self._http_client.post(
            self._app_url.with_path("/"),
            json=body,
            headers=self.COMMON_HEADERS,
            ssl=ssl_context,
        )
        _LOGGER.debug(
            "%s posted at %s. Host is %s, Response status is %s",
            step_name,
            datetime.now(),
            self._host,
            status,
        )
        if status != 200 or not isinstance(data, dict):
            raise KasaException(
                f"TPAP {step_name} failed for {self._host}: {status} {type(data)}"
            )

        self._handle_login_error_code(data, step_name)
        return self._require_result_dict(data)

    @staticmethod
    def _parse_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _require_result_dict(response: dict[str, Any]) -> dict[str, Any]:
        result = response.get("result")
        if not isinstance(result, dict):
            raise KasaException("TPAP response missing result object")
        return result

    def _get_error_code(self, response: dict[str, Any]) -> SmartErrorCode:
        error_code_raw = response.get("error_code")
        try:
            return SmartErrorCode.from_int(error_code_raw)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Device %s received unknown error code: %s",
                self._host,
                error_code_raw,
            )
            return SmartErrorCode.INTERNAL_UNKNOWN_ERROR

    def _handle_login_error_code(self, response: dict[str, Any], step: str) -> None:
        """Handle the error code of a login step.

        The device counts every rejected pake_share toward a lockout (15 on a
        KH100), so a failed pake_share is never raised as retryable. A locked
        device answers every step, even discover, with ``error_info`` holding
        ``lockedMinute`` and ``remainAttempts``.
        """
        error_code = self._get_error_code(response)
        if error_code is SmartErrorCode.SUCCESS:
            return

        error_info = response.get("error_info")
        if not isinstance(error_info, dict):
            error_info = {}
        locked_minutes = self._parse_optional_int(error_info.get("lockedMinute"))
        remain_attempts = self._parse_optional_int(error_info.get("remainAttempts"))
        host = self._host
        if (locked_minutes or 0) > 0 or remain_attempts == 0:
            self._invalidate_session()
            msg = f"TPAP {step} failed for {host}: device blocked after failed logins"
            if locked_minutes:
                msg += f", retry in {locked_minutes} minutes"
            raise DeviceError(msg, error_code=SmartErrorCode.DEVICE_BLOCKED)

        if step == "pake_share":
            self._invalidate_session()
            attempts_left = (
                f", {remain_attempts} attempts left before the device locks"
                if remain_attempts is not None
                else ""
            )
            if (
                error_code is SmartErrorCode.STAT_ACCESS_ERROR
                or error_code in SMART_AUTHENTICATION_ERRORS
            ):
                raise AuthenticationError(
                    f"TPAP {step} failed for {host}: credentials rejected by device "
                    f"({error_code.name}){attempts_left}",
                    error_code=error_code,
                )
            raise DeviceError(
                f"TPAP {step} failed for {host}: "
                f"{error_code.name}({error_code.value}){attempts_left}",
                error_code=error_code,
            )

        # Nothing has been proven before pake_share, so these steps may be retried.
        self._handle_response_error_code(response, step)

    def _handle_response_error_code(
        self, response: dict[str, Any], action: str
    ) -> None:
        """Handle response errors to request reauth etc."""
        error_code = self._get_error_code(response)
        if error_code is SmartErrorCode.SUCCESS:
            return

        full = (
            f"TPAP {action} failed for {self._host}: "
            f"{error_code.name}({error_code.value})"
        )
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(full, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._invalidate_session()
            raise AuthenticationError(full, error_code=error_code)
        raise DeviceError(full, error_code=error_code)

    async def perform_login(self) -> None:
        """Log in with pake_register and pake_share, one credential at a time."""
        passcode_type = self._get_passcode_type()
        if passcode_type is None:
            raise AuthenticationError(
                f"TPAP: no supported passcode type for {self._host}"
            )

        candidate_secrets = self._get_candidate_secrets()
        if not candidate_secrets:
            raise AuthenticationError(
                f"TPAP: no credential candidates available for {self._host}"
            )

        register_username = self._get_register_username()
        candidate_count = len(candidate_secrets)
        last_error: KasaException | None = None

        for attempt, candidate_secret in enumerate(candidate_secrets, start=1):
            self._shared_key = None
            self._expected_dev_confirm = None
            self._dac_nonce_base64 = None
            self._user_random = None
            self._user_random = self._base64(secrets.token_bytes(32))
            register_params = {
                "sub_method": "pake_register",
                "username": register_username,
                "user_random": self._user_random,
                "cipher_suites": [1],
                "encryption": ["aes_128_ccm"],
                "passcode_type": passcode_type,
            }

            try:
                register_result = await self._login(
                    register_params, step_name="pake_register"
                )
                _LOGGER.debug(
                    "pake_register success at %s. Host is %s",
                    datetime.now(),
                    self._host,
                )
                credentials_string = self._resolve_credentials(
                    register_result,
                    candidate_secret,
                    passcode_type=passcode_type,
                )
                share_params = self._build_share_params_from_register(
                    register_result, credentials_string
                )
                if self._use_dac_certification():
                    self._dac_nonce_base64 = self._base64(secrets.token_bytes(32))
                    share_params["dac_nonce"] = self._dac_nonce_base64

                share_result = await self._login(share_params, step_name="pake_share")
                self._establish_session_from_share_result(share_result)
                _LOGGER.debug(
                    "pake_share confirmation matches the expected credentials "
                    "(candidate %d/%d)",
                    attempt,
                    candidate_count,
                )
                return
            except (_RetryableError, _ConnectionError):
                raise
            except KasaException as exc:
                if getattr(exc, "error_code", None) is SmartErrorCode.DEVICE_BLOCKED:
                    raise
                last_error = exc
                if attempt < candidate_count:
                    _LOGGER.debug(
                        "credential candidate %d/%d failed for %s: %s",
                        attempt,
                        candidate_count,
                        self._host,
                        exc,
                    )

        if last_error is not None:
            if self._uses_camera_auth and 2 in (self._tpap_pake or []):
                _LOGGER.debug(
                    "all password-based camera candidates failed for %s",
                    self._host,
                )
            raise last_error

        raise KasaException(  # pragma: no cover
            "TPAP: handshake did not produce a session"
        )

    def _get_register_username(self) -> str:
        # Only cameras hash the user name as user_hash_type says
        return (
            crypto.sha256_hex_upper("admin")
            if self._uses_camera_auth and self._tpap_user_hash_type == 1
            else crypto.md5_hex("admin")
        )

    @staticmethod
    def _base64(value: bytes) -> str:
        return base64.b64encode(value).decode()

    @staticmethod
    def _unbase64(value: str) -> bytes:
        return base64.b64decode(value)

    def _use_dac_certification(self) -> bool:
        # Attestation with tls 0 and dac, for the default passcode (pake 0)
        # and on Tapo IoT devices also pake 5; never on cameras
        if self._tpap_tls != 0 or not self._tpap_dac or self._uses_camera_auth:
            return False
        pake = self._tpap_pake or []
        if 0 in pake:
            return True
        kasa_or_robot = self._uses_kasa_iot_auth or self._uses_robot_tpap_auth
        return 5 in pake and not kasa_or_robot

    def _get_passcode_type(self) -> str | None:
        passcode_type_order: tuple[tuple[tuple[int, ...], str], ...]
        default_passcode_type: str | None

        if self._uses_camera_auth:
            passcode_type_order = (
                ((2, 1), "userpw"),
                ((0,), "default_userpw"),
                ((3,), "shared_token"),
            )
            default_passcode_type = None
        elif self._uses_robot_tpap_auth:
            passcode_type_order = (
                ((0,), "default_userpw"),
                ((2,), "userpw"),
                ((3,), "shared_token"),
            )
            default_passcode_type = "default_userpw"
        elif self._uses_kasa_iot_auth:
            # Kasa devices take the password whenever pake has 2, so 2 wins
            # over 0, and anything else gets the default
            passcode_type_order = (
                ((2,), "userpw"),
                ((3,), "shared_token"),
            )
            default_passcode_type = "default_userpw"
        else:
            passcode_type_order = (
                ((0,), "default_userpw"),
                ((2, 5), "userpw"),
                ((3,), "shared_token"),
            )
            default_passcode_type = "default_userpw"

        if self._tpap_pake is None:
            # No announced passcode types, nothing to log in with
            return None
        pake = set(self._tpap_pake)
        for pake_values, passcode_type in passcode_type_order:
            if pake.intersection(pake_values):
                return passcode_type
        return default_passcode_type

    def _get_candidate_secrets(self, passcode_type: str | None = None) -> list[str]:
        passcode_type = passcode_type or self._get_passcode_type()
        if passcode_type is None:
            return []
        if passcode_type == "default_userpw":
            return (
                [crypto.mac_pass_from_device_mac(self._device_mac)]
                if self._device_mac
                else []
            )
        creds = self._config.credentials
        password = (creds.password if creds else "") or ""
        if not password:
            # Each candidate is a login the device counts toward its lockout
            return []
        if not self._uses_camera_auth:
            return [password]
        if passcode_type == "shared_token":
            return [crypto.md5_hex(password)]
        if 2 not in (self._tpap_pake or []):
            return [password]
        return list(
            dict.fromkeys(
                [
                    crypto.md5_hex(password),
                    crypto.sha256_hex_upper(password),
                ]
            )
        )

    def _resolve_credentials(
        self,
        register_result: dict[str, Any],
        candidate_secret: str,
        *,
        passcode_type: str | None = None,
    ) -> str:
        if (passcode_type or self._get_passcode_type()) == "default_userpw":
            return candidate_secret
        extra_crypt_value = register_result.get("extra_crypt")
        extra_crypt = extra_crypt_value if isinstance(extra_crypt_value, dict) else {}
        if self._uses_camera_auth and not extra_crypt:
            return candidate_secret
        creds = self._config.credentials
        username = (
            "" if self._uses_camera_auth else (creds.username if creds else "") or ""
        )
        mac_no_colon = self._device_mac.replace(":", "").replace("-", "")
        return crypto.build_credentials(
            extra_crypt,
            username,
            candidate_secret,
            mac_no_colon,
        )

    def _build_share_params_from_register(
        self, register_result: dict[str, Any], credentials_string: str
    ) -> dict[str, Any]:
        if self._user_random is None:
            raise KasaException("TPAP user random not initialized")

        dev_random = str(register_result.get("dev_random") or "")
        dev_salt = str(register_result.get("dev_salt") or "")
        dev_share = str(register_result.get("dev_share") or "")
        for field, value in (
            ("dev_random", dev_random),
            ("dev_salt", dev_salt),
            ("dev_share", dev_share),
        ):
            if not value:
                raise KasaException(f"TPAP register response missing {field}")

        suite_type_value = register_result.get("cipher_suites")
        if suite_type_value is None:
            raise KasaException("TPAP register response has invalid cipher_suites")
        try:
            suite_type = int(suite_type_value)
        except (TypeError, ValueError) as exc:
            raise KasaException(
                "TPAP register response has invalid cipher_suites"
            ) from exc

        iterations_value = register_result.get("iterations")
        if iterations_value is None:
            iterations_value = self.DEFAULT_PAKE_ITERATIONS
        try:
            iterations = int(iterations_value)
        except (TypeError, ValueError) as exc:
            raise KasaException(
                "TPAP register response has invalid iterations"
            ) from exc

        if iterations <= 0 or iterations > self.MAX_PAKE_ITERATIONS:
            raise KasaException("TPAP register response has invalid iterations")

        encryption = str(register_result.get("encryption") or "")
        if not encryption:
            raise KasaException("TPAP register response missing encryption")
        chosen_cipher = TpapEncryptionSession._normalize_cipher_id(encryption)
        if chosen_cipher not in TpapEncryptionSession.CIPHER_PARAMETERS:
            raise KasaException(f"Unsupported TPAP session cipher: {encryption}")

        self._cipher_id = chosen_cipher
        user_share, user_confirm, expected_dev_confirm, self._shared_key = (
            crypto.spake2p_share(
                credentials_string.encode(),
                suite_type=suite_type,
                salt=self._unbase64(dev_salt),
                iterations=iterations,
                user_random=self._unbase64(self._user_random),
                dev_random=self._unbase64(dev_random),
                dev_share=self._unbase64(dev_share),
            )
        )
        self._expected_dev_confirm = self._base64(expected_dev_confirm)
        return {
            "sub_method": "pake_share",
            "user_share": self._base64(user_share),
            "user_confirm": self._base64(user_confirm),
        }

    def _verify_dac_proof(self, share_result: dict[str, Any]) -> None:
        """Verify DAC certificate chain and proof signature.

        Called when the attestation was asked for. A reply without the
        certificate or the proof fails; the intermediate is optional.
        """
        try:
            dac_ca = str(share_result.get("dac_ca") or "")
            dac_ica = str(share_result.get("dac_ica") or "")
            dac_proof = share_result.get("dac_proof")
            if not dac_ca or not dac_proof:
                raise KasaException("device sent no DAC certificate or proof")
            if not self._shared_key or not self._dac_nonce_base64:
                raise KasaException("no shared key or DAC nonce to check it with")
            if not isinstance(dac_proof, str):
                raise KasaException("Invalid DAC proof type")

            cert.verify_dac_proof(
                dac_ca,
                dac_ica,
                dac_proof,
                self._shared_key + self._unbase64(self._dac_nonce_base64),
            )
        except InvalidSignature as exc:
            _LOGGER.error("invalid DAC proof signature")
            raise KasaException("Invalid DAC proof signature") from exc
        except Exception as exc:
            _LOGGER.error("DAC verification failed: %s", exc)
            raise KasaException(f"DAC verification failed: {exc}") from exc

    def _establish_session_from_share_result(
        self, share_result: dict[str, Any]
    ) -> None:
        dev_confirm = str(share_result.get("dev_confirm") or "")
        if not dev_confirm:
            raise KasaException("TPAP share response missing dev_confirm")
        # base64 is case-sensitive, so the strings are compared exactly
        if not hmac.compare_digest(
            dev_confirm.encode(), (self._expected_dev_confirm or "").encode()
        ):
            raise KasaException("TPAP confirmation mismatch")

        if self._use_dac_certification():
            self._verify_dac_proof(share_result)

        session_id = str(
            share_result.get("sessionId") or share_result.get("stok") or ""
        )
        if not session_id:
            _LOGGER.error("missing session ID from device")
            raise KasaException("Missing session fields from device")
        if self._shared_key is None:
            raise KasaException("TPAP shared key was not derived")
        start_seq = share_result.get("start_seq")
        if start_seq is None:
            raise KasaException("Missing session fields from device")
        try:
            sequence = int(start_seq)
        except (TypeError, ValueError) as exc:
            raise KasaException("Invalid session fields from device") from exc

        self._encryption_session = TpapEncryptionSession(
            self._cipher_id, self._shared_key, sequence
        )
        self._ds_url = URL(f"{self._app_url}/stok={session_id}/ds")

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        if self._encryption_session is None:
            await self.perform_handshake()

        async with self._send_lock:
            session, ds_url = self._encryption_session, self._ds_url
            if session is None or ds_url is None:
                raise KasaException("TPAP transport is not established")
            payload, seq = session.encrypt(request)
            headers = {"Content-Type": "application/octet-stream"}
            ssl_context = await self.get_ssl_context()
            status, data = await self._http_client.post(
                ds_url,
                data=payload,
                headers=headers,
                ssl=ssl_context,
            )
            msg = (
                f"Host is {self._host}, Sequence is {seq}, "
                f"Response status is {status}, Request was {request}"
            )
            if status != 200:
                # Debug, not error: a dropped session is logged in again
                _LOGGER.debug("Device %s query failed: %s", self._host, msg)
                self._raise_if_session_lost(data)
                raise KasaException(
                    f"TPAP secure request failed for {self._host}: status {status}"
                )
            _LOGGER.debug("Device %s query posted %s", self._host, msg)

        if isinstance(data, bytes | bytearray):
            plaintext = session.decrypt(bytes(data), seq)
            _LOGGER.debug("Device %s query response received", self._host)
            return self._load_json_dict(plaintext)

        if isinstance(data, dict):
            self._raise_if_session_lost(data)
            self._handle_response_error_code(data, "request")
            return data

        raise KasaException("Unexpected TPAP response body type")

    def _raise_if_session_lost(self, data: Any) -> None:
        """Drop the session and raise a retryable error if the device dropped it."""
        if isinstance(data, bytes | bytearray):
            try:
                data = json_loads(bytes(data).decode())
            except (UnicodeDecodeError, ValueError):
                return
        if not isinstance(data, dict):
            return
        error_code = data.get("error_code", data.get("err_code"))
        if error_code not in self.SESSION_LOST_ERROR_CODES:
            return
        self._reset_state()
        try:
            smart_error_code = SmartErrorCode.from_int(error_code)
        except ValueError:
            smart_error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR
        raise _RetryableError(
            f"TPAP request failed for {self._host}: device dropped the session "
            f"({error_code})",
            error_code=smart_error_code,
        )

    @staticmethod
    def _load_json_dict(payload: bytes) -> dict[str, Any]:
        response_data = json_loads(payload.decode())
        if not isinstance(response_data, dict):
            raise KasaException("Unexpected TPAP JSON response body type")
        return response_data

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal transport state."""
        self._reset_state()

    def _reset_state(self) -> None:
        """Drop the session and go back to the initial URL and TLS context."""
        self._ssl_context = None
        self._app_url = self._get_initial_app_url()
        self._invalidate_session()

    def _invalidate_session(self) -> None:
        """Drop the session and the login state, keeping the login values."""
        self._encryption_session = None
        self._ds_url = None
        self._cipher_id = "aes_128_ccm"
        self._shared_key = None
        self._expected_dev_confirm = None
        self._dac_nonce_base64 = None
        self._user_random = None


class TpapEncryptionSession:
    """An established TPAP session: its cipher, key, nonce and sequence."""

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

    def __init__(self, cipher_id: str, shared_key: bytes, start_seq: int) -> None:
        self._cipher_id = cipher_id
        self._key, self._base_nonce = self.key_nonce_from_shared(shared_key, cipher_id)
        self._sequence = start_seq

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
        cls, shared_key: bytes, cipher_id: str
    ) -> tuple[bytes, bytes]:
        """Derive the session key and base nonce.

        Both use HKDF-SHA256 whatever the cipher suite; only the SPAKE2+
        transcript and its keys use the suite's hash.
        """
        key_salt, key_info, nonce_salt, nonce_info, key_len = cls._cipher_parameters(
            cipher_id
        )
        return (
            cls._hkdf(
                shared_key,
                salt=key_salt,
                info=key_info,
                length=key_len,
            ),
            cls._hkdf(
                shared_key,
                salt=nonce_salt,
                info=nonce_info,
                length=cls.NONCE_LEN,
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

    def encrypt(self, payload: bytes | str) -> tuple[bytes, int]:
        """Encrypt the message."""
        cipher_id, seq = self._cipher_id, self._sequence
        key, base_nonce = self._key, self._base_nonce
        plaintext = payload.encode() if isinstance(payload, str) else payload
        encrypted = self._encrypt_payload(cipher_id, key, base_nonce, plaintext, seq)
        self._sequence = seq + 1
        return struct.pack(">I", seq) + encrypted, seq

    def decrypt(self, payload: bytes, request_seq: int) -> bytes:
        """Decrypt the message."""
        cipher_id, key, base_nonce = self._cipher_id, self._key, self._base_nonce
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
