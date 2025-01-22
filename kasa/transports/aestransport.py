"""Implementation of the TP-Link AES transport.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from collections.abc import AsyncGenerator
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, Credentials, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    TimeoutError,
    _ConnectionError,
    _RetryableError,
)
from kasa.httpclient import HttpClient
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads

from .basetransport import BaseTransport

_LOGGER = logging.getLogger(__name__)


ONE_DAY_SECONDS = 86400
SESSION_EXPIRE_BUFFER_SECONDS = 60 * 20


def _sha1(payload: bytes) -> str:
    sha1_algo = hashlib.sha1()  # noqa: S324
    sha1_algo.update(payload)
    return sha1_algo.hexdigest()


class TransportState(Enum):
    """Enum for AES state."""

    HANDSHAKE_REQUIRED = auto()  # Handshake needed
    LOGIN_REQUIRED = auto()  # Login needed
    ESTABLISHED = auto()  # Ready to send requests


class AesTransport(BaseTransport):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT: int = 80
    SESSION_COOKIE_NAME = "TP_SESSIONID"
    TIMEOUT_COOKIE_NAME = "TIMEOUT"
    COMMON_HEADERS = {
        "Content-Type": "application/json",
        "requestByApp": "true",
        "Accept": "application/json",
    }
    CONTENT_LENGTH = "Content-Length"
    KEY_PAIR_CONTENT_LENGTH = 314

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
        if self._credentials:
            self._login_params = self._get_login_params(self._credentials)
        else:
            self._login_params = json_loads(
                base64.b64decode(self._credentials_hash.encode()).decode()  # type: ignore[union-attr]
            )
        self._default_credentials: Credentials | None = None
        self._http_client: HttpClient = HttpClient(config)

        self._state = TransportState.HANDSHAKE_REQUIRED

        self._encryption_session: AesEncyptionSession | None = None
        self._session_expire_at: float | None = None

        self._session_cookie: dict[str, str] | None = None

        self._key_pair: KeyPair | None = None
        if config.aes_keys:
            aes_keys = config.aes_keys
            self._key_pair = KeyPair.create_from_der_keys(
                aes_keys["private"], aes_keys["public"]
            )
        self._app_url = URL(f"http://{self._host}:{self._port}/app")
        self._token_url: URL | None = None

        _LOGGER.debug("Created AES transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""
        if self._credentials == Credentials():
            return None
        return base64.b64encode(json_dumps(self._login_params).encode()).decode()

    def _get_login_params(self, credentials: Credentials) -> dict[str, str]:
        """Get the login parameters based on the login_version."""
        un, pw = self.hash_credentials(self._login_version == 2, credentials)
        password_field_name = "password2" if self._login_version == 2 else "password"
        return {password_field_name: pw, "username": un}

    @staticmethod
    def hash_credentials(login_v2: bool, credentials: Credentials) -> tuple[str, str]:
        """Hash the credentials."""
        un = base64.b64encode(_sha1(credentials.username.encode()).encode()).decode()
        if login_v2:
            pw = base64.b64encode(
                _sha1(credentials.password.encode()).encode()
            ).decode()
        else:
            pw = base64.b64encode(credentials.password.encode()).decode()
        return un, pw

    def _handle_response_error_code(self, resp_dict: dict, msg: str) -> None:
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR
        if error_code is SmartErrorCode.SUCCESS:
            return
        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.HANDSHAKE_REQUIRED
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

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
        status_code, resp_dict = await self._http_client.post(
            url,
            json=passthrough_request,
            headers=self.COMMON_HEADERS,
            cookies_dict=self._session_cookie,
        )
        # _LOGGER.debug(f"secure_passthrough response is {status_code}: {resp_dict}")

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        if TYPE_CHECKING:
            resp_dict = cast(dict[str, Any], resp_dict)
            assert self._encryption_session is not None

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        raw_response: str = resp_dict["result"]["response"]

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

    async def perform_login(self) -> None:
        """Login to the device."""
        try:
            await self.try_login(self._login_params)
            _LOGGER.debug(
                "%s: logged in with provided credentials",
                self._host,
            )
        except AuthenticationError as aex:
            try:
                if aex.error_code is not SmartErrorCode.LOGIN_ERROR:
                    raise aex
                _LOGGER.debug(
                    "%s: trying login with default TAPO credentials",
                    self._host,
                )
                if self._default_credentials is None:
                    self._default_credentials = get_default_credentials(
                        DEFAULT_CREDENTIALS["TAPO"]
                    )
                await self.perform_handshake()
                await self.try_login(self._get_login_params(self._default_credentials))
                _LOGGER.debug(
                    "%s: logged in with default TAPO credentials",
                    self._host,
                )
            except (AuthenticationError, _ConnectionError, TimeoutError):
                raise
            except Exception as ex:
                raise KasaException(
                    "Unable to login and trying default "
                    + f"login raised another exception: {ex}",
                    ex,
                ) from ex

    async def try_login(self, login_params: dict[str, Any]) -> None:
        """Try to login with supplied login_params."""
        login_request = {
            "method": "login_device",
            "params": login_params,
            "request_time_milis": round(time.time() * 1000),
        }
        request = json_dumps(login_request)

        resp_dict = await self.send_secure_passthrough(request)
        self._handle_response_error_code(resp_dict, "Error logging in")
        login_token = resp_dict["result"]["token"]
        self._token_url = self._app_url.with_query(f"token={login_token}")
        self._state = TransportState.ESTABLISHED

    async def _generate_key_pair_payload(self) -> AsyncGenerator:
        """Generate the request body and return an ascyn_generator.

        This prevents the key pair being generated unless a connection
        can be made to the device.
        """
        _LOGGER.debug("Generating keypair")
        if not self._key_pair:
            kp = KeyPair.create_key_pair()
            self._config.aes_keys = {
                "private": kp.private_key_der_b64,
                "public": kp.public_key_der_b64,
            }
            self._key_pair = kp

        pub_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            + self._key_pair.public_key_der_b64  # type: ignore[union-attr]
            + "\n-----END PUBLIC KEY-----\n"
        )
        handshake_params = {"key": pub_key}
        request_body = {"method": "handshake", "params": handshake_params}
        _LOGGER.debug("Handshake request: %s", request_body)
        yield json_dumps(request_body).encode()

    async def perform_handshake(self) -> None:
        """Perform the handshake."""
        _LOGGER.debug("Will perform handshaking...")

        self._token_url = None
        self._session_expire_at = None
        self._session_cookie = None

        # Device needs the content length or it will response with 500
        headers = {
            **self.COMMON_HEADERS,
            self.CONTENT_LENGTH: str(self.KEY_PAIR_CONTENT_LENGTH),
        }
        http_client = self._http_client

        status_code, resp_dict = await http_client.post(
            self._app_url,
            json=self._generate_key_pair_payload(),
            headers=headers,
            cookies_dict=self._session_cookie,
        )

        _LOGGER.debug("Device responded with: %s", resp_dict)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake"
            )

        if TYPE_CHECKING:
            resp_dict = cast(dict[str, Any], resp_dict)

        self._handle_response_error_code(resp_dict, "Unable to complete handshake")

        handshake_key = resp_dict["result"]["key"]

        if (
            cookie := http_client.get_cookie(self.SESSION_COOKIE_NAME)  # type: ignore
        ) or (
            cookie := http_client.get_cookie("SESSIONID")  # type: ignore
        ):
            self._session_cookie = {self.SESSION_COOKIE_NAME: cookie}

        timeout = int(
            http_client.get_cookie(self.TIMEOUT_COOKIE_NAME) or ONE_DAY_SECONDS
        )
        # There is a 24 hour timeout on the session cookie
        # but the clock on the device is not always accurate
        # so we set the expiry to 24 hours from now minus a buffer
        self._session_expire_at = time.time() + timeout - SESSION_EXPIRE_BUFFER_SECONDS
        if TYPE_CHECKING:
            assert self._key_pair is not None
        self._encryption_session = AesEncyptionSession.create_from_keypair(
            handshake_key, self._key_pair
        )

        self._state = TransportState.LOGIN_REQUIRED

        _LOGGER.debug("Handshake with %s complete", self._host)

    def _handshake_session_expired(self) -> bool:
        """Return true if session has expired."""
        return (
            self._session_expire_at is None
            or self._session_expire_at - time.time() <= 0
        )

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        if (
            self._state is TransportState.HANDSHAKE_REQUIRED
            or self._handshake_session_expired()
        ):
            await self.perform_handshake()
        if self._state is not TransportState.ESTABLISHED:
            try:
                await self.perform_login()
            # After a login failure handshake needs to
            # be redone or a 9999 error is received.
            except AuthenticationError as ex:
                self._state = TransportState.HANDSHAKE_REQUIRED
                raise ex

        return await self.send_secure_passthrough(request)

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal handshake and login state."""
        self._state = TransportState.HANDSHAKE_REQUIRED


class AesEncyptionSession:
    """Class for an AES encryption session."""

    @staticmethod
    def create_from_keypair(
        handshake_key: str, keypair: KeyPair
    ) -> AesEncyptionSession:
        """Create the encryption session."""
        handshake_key_bytes: bytes = base64.b64decode(handshake_key.encode())

        key_and_iv = keypair.decrypt_handshake_key(handshake_key_bytes)
        if key_and_iv is None:
            raise ValueError("Decryption failed!")

        return AesEncyptionSession(key_and_iv[:16], key_and_iv[16:])

    def __init__(self, key: bytes, iv: bytes) -> None:
        self.cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        self.padding_strategy = padding.PKCS7(algorithms.AES.block_size)

    def encrypt(self, data: bytes) -> bytes:
        """Encrypt the message."""
        encryptor = self.cipher.encryptor()
        padder = self.padding_strategy.padder()
        padded_data = padder.update(data) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(encrypted)

    def decrypt(self, data: str | bytes) -> str:
        """Decrypt the message."""
        decryptor = self.cipher.decryptor()
        unpadder = self.padding_strategy.unpadder()
        decrypted = decryptor.update(base64.b64decode(data)) + decryptor.finalize()
        unpadded_data = unpadder.update(decrypted) + unpadder.finalize()
        return unpadded_data.decode()


class KeyPair:
    """Class for generating key pairs."""

    @staticmethod
    def create_key_pair(key_size: int = 1024) -> KeyPair:
        """Create a key pair."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        public_key = private_key.public_key()
        return KeyPair(private_key, public_key)

    @staticmethod
    def create_from_der_keys(
        private_key_der_b64: str, public_key_der_b64: str
    ) -> KeyPair:
        """Create a key pair."""
        key_bytes = base64.b64decode(private_key_der_b64.encode())
        private_key = cast(
            rsa.RSAPrivateKey, serialization.load_der_private_key(key_bytes, None)
        )
        key_bytes = base64.b64decode(public_key_der_b64.encode())
        public_key = cast(
            rsa.RSAPublicKey, serialization.load_der_public_key(key_bytes, None)
        )

        return KeyPair(private_key, public_key)

    def __init__(
        self, private_key: rsa.RSAPrivateKey, public_key: rsa.RSAPublicKey
    ) -> None:
        self.private_key = private_key
        self.public_key = public_key
        self.private_key_der_bytes = self.private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_key_der_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.private_key_der_b64 = base64.b64encode(self.private_key_der_bytes).decode()
        self.public_key_der_b64 = base64.b64encode(self.public_key_der_bytes).decode()

    def get_public_pem(self) -> bytes:
        """Get public key in PEM encoding."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def decrypt_handshake_key(self, encrypted_key: bytes) -> bytes:
        """Decrypt an aes handshake key."""
        decrypted = self.private_key.decrypt(
            encrypted_key, asymmetric_padding.PKCS1v15()
        )
        return decrypted

    def decrypt_discovery_key(self, encrypted_key: bytes) -> bytes:
        """Decrypt an aes discovery key."""
        decrypted = self.private_key.decrypt(
            encrypted_key,
            asymmetric_padding.OAEP(
                mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303
                algorithm=hashes.SHA1(),  # noqa: S303
                label=None,
            ),
        )
        return decrypted
