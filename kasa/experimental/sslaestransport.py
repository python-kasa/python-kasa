"""Implementation of the TP-Link SSL AES transport."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import ssl
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, cast

from yarl import URL

from ..aestransport import AesEncyptionSession
from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from ..httpclient import HttpClient
from ..json import dumps as json_dumps
from ..json import loads as json_loads
from ..protocol import DEFAULT_CREDENTIALS, BaseTransport, get_default_credentials

_LOGGER = logging.getLogger(__name__)


ONE_DAY_SECONDS = 86400
SESSION_EXPIRE_BUFFER_SECONDS = 60 * 20


def _sha256(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()  # noqa: S324


def _md5_hash(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest().upper()  # noqa: S324


def _sha256_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()  # noqa: S324


class TransportState(Enum):
    """Enum for AES state."""

    HANDSHAKE_REQUIRED = auto()  # Handshake needed
    ESTABLISHED = auto()  # Ready to send requests


class SslAesTransport(BaseTransport):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT: int = 443
    COMMON_HEADERS = {
        "Content-Type": "application/json; charset=UTF-8",
        "requestByApp": "true",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "Tapo CameraClient Android",
    }
    CIPHERS = ":".join(
        [
            "AES256-GCM-SHA384",
            "AES256-SHA256",
            "AES128-GCM-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
        ]
    )
    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        super().__init__(config=config)

        self._login_version = config.connection_type.login_version
        if (
            not self._credentials or self._credentials.username is None
        ) and not self._credentials_hash:
            self._credentials = Credentials()
        self._default_credentials: Credentials = get_default_credentials(
            DEFAULT_CREDENTIALS["TAPOCAMERA"]
        )
        self._http_client: HttpClient = HttpClient(config)

        self._state = TransportState.HANDSHAKE_REQUIRED

        self._encryption_session: AesEncyptionSession | None = None
        self._session_expire_at: float | None = None

        self._host_port = f"{self._host}:{self._port}"
        self._app_url = URL(f"https://{self._host_port}")
        self._token_url: URL | None = None
        self._ssl_context: ssl.SSLContext | None = None
        ref = str(self._token_url) if self._token_url else str(self._app_url)
        self._headers = {
            **self.COMMON_HEADERS,
            "Host": self._host_port,
            "Referer": ref,
        }
        self._seq: int | None = None
        self._pwd_hash: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        if self._credentials != Credentials() and self._credentials:
            self._username = self._credentials.username
            self._password = self._credentials.password
        elif self._credentials_hash:
            ch = json_loads(base64.b64decode(self._credentials_hash.encode()))
            self._password = ch["pwd"]
            self._username = ch["un"]
        self._local_nonce: str | None = None

        _LOGGER.debug("Created AES transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        return self.DEFAULT_PORT

    @staticmethod
    def _create_b64_credentials(credentials: Credentials) -> str:
        ch = {"un": credentials.username, "pwd": credentials.password}
        return base64.b64encode(json_dumps(ch).encode()).decode()

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""
        if self._credentials == Credentials():
            return None
        if not self._credentials and self._credentials_hash:
            return self._credentials_hash
        if (cred := self._credentials) and cred.password and cred.username:
            return self._create_b64_credentials(cred)
        return None

    def _get_response_error(self, resp_dict: Any) -> SmartErrorCode:
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR
        return error_code

    def _handle_response_error_code(self, resp_dict: Any, msg: str) -> None:
        error_code = self._get_response_error(resp_dict)
        if error_code is SmartErrorCode.SUCCESS:
            return
        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.HANDSHAKE_REQUIRED
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext()
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    async def _get_ssl_context(self) -> ssl.SSLContext:
        if not self._ssl_context:
            loop = asyncio.get_running_loop()
            self._ssl_context = await loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    async def send_secure_passthrough(self, request: str) -> dict[str, Any]:
        """Send encrypted message as passthrough."""
        if self._state is TransportState.ESTABLISHED and self._token_url:
            url = self._token_url
        else:
            url = self._app_url

        encrypted_payload = self._encryption_session.encrypt(request.encode())  # type: ignore
        passthrough_request = {
            "method": "securePassthrough",
            "params": {"request": encrypted_payload.decode()},
        }
        passthrough_request_str = json_dumps(passthrough_request)
        if TYPE_CHECKING:
            assert self._pwd_hash
            assert self._local_nonce
            assert self._seq
        tag = self.generate_tag(
            passthrough_request_str, self._local_nonce, self._pwd_hash, self._seq
        )
        headers = {**self._headers, "Seq": str(self._seq), "Tapo_tag": tag}
        self._seq += 1
        status_code, resp_dict = await self._http_client.post(
            url,
            json=passthrough_request_str,
            headers=headers,
            ssl=await self._get_ssl_context(),
        )

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        if TYPE_CHECKING:
            resp_dict = cast(Dict[str, Any], resp_dict)
            assert self._encryption_session is not None

        if "result" in resp_dict and "response" in resp_dict["result"]:
            raw_response: str = resp_dict["result"]["response"]
        else:
            # Tapo Cameras respond unencrypted to single requests.
            return resp_dict

        try:
            response = self._encryption_session.decrypt(raw_response.encode())
            ret_val = json_loads(response)
        except Exception as ex:
            try:
                ret_val = json_loads(raw_response)
                _LOGGER.debug(
                    "Received unencrypted response over secure passthrough from %s",
                    self._host,
                )
            except Exception:
                raise KasaException(
                    f"Unable to decrypt response from {self._host}, "
                    + f"error: {ex}, response: {raw_response}",
                    ex,
                ) from ex
        return ret_val  # type: ignore[return-value]

    @staticmethod
    def generate_confirm_hash(local_nonce, server_nonce, pwd_hash):
        """Generate an auth hash for the protocol on the supplied credentials."""
        expected_confirm_bytes = _sha256_hash(
            local_nonce.encode() + pwd_hash.encode() + server_nonce.encode()
        )
        return expected_confirm_bytes + server_nonce + local_nonce

    @staticmethod
    def generate_digest_password(local_nonce, server_nonce, pwd_hash):
        """Generate an auth hash for the protocol on the supplied credentials."""
        digest_password_hash = _sha256_hash(
            pwd_hash.encode() + local_nonce.encode() + server_nonce.encode()
        )
        return (
            digest_password_hash.encode() + local_nonce.encode() + server_nonce.encode()
        ).decode()

    @staticmethod
    def generate_encryption_token(
        token_type, local_nonce, server_nonce, pwd_hash
    ) -> bytes:
        """Generate encryption token."""
        hashedKey = _sha256_hash(
            local_nonce.encode() + pwd_hash.encode() + server_nonce.encode()
        )
        return _sha256(
            token_type.encode()
            + local_nonce.encode()
            + server_nonce.encode()
            + hashedKey.encode()
        )[:16]

    @staticmethod
    def generate_tag(request: str, local_nonce: str, pwd_hash: str, seq: int) -> str:
        """Generate the tag header from the request for the header."""
        pwd_nonce_hash = _sha256_hash(pwd_hash.encode() + local_nonce.encode())
        tag = _sha256_hash(
            pwd_nonce_hash.encode() + request.encode() + str(seq).encode()
        )
        return tag

    async def perform_handshake(self) -> None:
        """Perform the handshake."""
        local_nonce, server_nonce, pwd_hash = await self.perform_handshake1()
        await self.perform_handshake2(local_nonce, server_nonce, pwd_hash)

    async def perform_handshake2(self, local_nonce, server_nonce, pwd_hash) -> None:
        """Perform the handshake."""
        _LOGGER.debug("Performing handshake2 ...")
        digest_password = self.generate_digest_password(
            local_nonce, server_nonce, pwd_hash
        )
        body = {
            "method": "login",
            "params": {
                "cnonce": local_nonce,
                "encrypt_type": "3",
                "digest_passwd": digest_password,
                "username": self._username,
            },
        }
        http_client = self._http_client
        status_code, resp_dict = await http_client.post(
            self._app_url,
            json=body,
            headers=self._headers,
            ssl=await self._get_ssl_context(),
        )
        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake2"
            )
        resp_dict = cast(dict, resp_dict)
        if (
            error_code := self._get_response_error(resp_dict)
        ) and error_code is SmartErrorCode.INVALID_NONCE:
            raise AuthenticationError(
                f"Invalid password hash in handshake2 for {self._host}"
            )

        self._handle_response_error_code(resp_dict, "Error in handshake2")

        self._seq = resp_dict["result"]["start_seq"]
        stok = resp_dict["result"]["stok"]
        self._token_url = URL(f"{str(self._app_url)}/stok={stok}/ds")
        self._pwd_hash = pwd_hash
        self._local_nonce = local_nonce
        lsk = self.generate_encryption_token("lsk", local_nonce, server_nonce, pwd_hash)
        ivb = self.generate_encryption_token("ivb", local_nonce, server_nonce, pwd_hash)
        self._encryption_session = AesEncyptionSession(lsk, ivb)
        self._state = TransportState.ESTABLISHED
        _LOGGER.debug("Handshake2 complete ...")

    async def perform_handshake1(self) -> tuple[str, str, str]:
        """Perform the handshake1."""
        resp_dict = None
        if self._username:
            local_nonce = secrets.token_bytes(8).hex().upper()
            resp_dict = await self.try_send_handshake1(self._username, local_nonce)

        # Try the default username. If it fails raise the original error_code
        if (
            not resp_dict
            or (error_code := self._get_response_error(resp_dict))
            is not SmartErrorCode.INVALID_NONCE
            or "nonce" not in resp_dict["result"].get("data", {})
        ):
            local_nonce = secrets.token_bytes(8).hex().upper()
            default_resp_dict = await self.try_send_handshake1(
                self._default_credentials.username, local_nonce
            )
            if (
                default_error_code := self._get_response_error(default_resp_dict)
            ) is SmartErrorCode.INVALID_NONCE and "nonce" in default_resp_dict[
                "result"
            ].get("data", {}):
                _LOGGER.debug("Connected to {self._host} with default username")
                self._username = self._default_credentials.username
                error_code = default_error_code
                resp_dict = default_resp_dict

        if not self._username:
            raise AuthenticationError(
                f"Credentials must be supplied to connect to {self._host}"
            )
        if error_code is not SmartErrorCode.INVALID_NONCE or (
            resp_dict and "nonce" not in resp_dict["result"].get("data", {})
        ):
            raise AuthenticationError(f"Error trying handshake1: {resp_dict}")

        if TYPE_CHECKING:
            resp_dict = cast(Dict[str, Any], resp_dict)

        server_nonce = resp_dict["result"]["data"]["nonce"]
        device_confirm = resp_dict["result"]["data"]["device_confirm"]
        if self._credentials and self._credentials != Credentials():
            pwd_hash = _sha256_hash(self._credentials.password.encode())
        elif self._username and self._password:
            pwd_hash = _sha256_hash(self._password.encode())
        else:
            pwd_hash = _sha256_hash(self._default_credentials.password.encode())

        expected_confirm_sha256 = self.generate_confirm_hash(
            local_nonce, server_nonce, pwd_hash
        )
        if device_confirm == expected_confirm_sha256:
            _LOGGER.debug("Credentials match")
            return local_nonce, server_nonce, pwd_hash

        if TYPE_CHECKING:
            assert self._credentials
            assert self._credentials.password
        pwd_hash = _md5_hash(self._credentials.password.encode())
        expected_confirm_md5 = self.generate_confirm_hash(
            local_nonce, server_nonce, pwd_hash
        )
        if device_confirm == expected_confirm_md5:
            _LOGGER.debug("Credentials match")
            return local_nonce, server_nonce, pwd_hash

        msg = f"Server response doesn't match our challenge on ip {self._host}"
        _LOGGER.debug(msg)
        raise AuthenticationError(msg)

    async def try_send_handshake1(self, username: str, local_nonce: str) -> dict:
        """Perform the handshake."""
        _LOGGER.debug("Will to send handshake1...")

        body = {
            "method": "login",
            "params": {
                "cnonce": local_nonce,
                "encrypt_type": "3",
                "username": username,
            },
        }
        http_client = self._http_client

        status_code, resp_dict = await http_client.post(
            self._app_url,
            json=body,
            headers=self._headers,
            ssl=await self._get_ssl_context(),
        )

        _LOGGER.debug("Device responded with: %s", resp_dict)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake1"
            )

        return cast(dict, resp_dict)

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        if self._state is TransportState.HANDSHAKE_REQUIRED:
            await self.perform_handshake()

        return await self.send_secure_passthrough(request)

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal handshake state."""
        self._state = TransportState.HANDSHAKE_REQUIRED
        self._encryption_session = None
        self._seq = 0
        self._pwd_hash = None
        self._local_nonce = None
