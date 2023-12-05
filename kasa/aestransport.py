"""Implementation of the TP-Link AES transport.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

import base64
import hashlib
import logging
import time
from typing import Optional

import httpx
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .connectionparams import ConnectionParameters
from .exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    SMART_TIMEOUT_ERRORS,
    AuthenticationException,
    RetryableException,
    SmartDeviceException,
    SmartErrorCode,
    TimeoutException,
)
from .json import dumps as json_dumps
from .json import loads as json_loads
from .protocol import BaseTransport

_LOGGER = logging.getLogger(__name__)


def _sha1(payload: bytes) -> str:
    sha1_algo = hashlib.sha1()  # noqa: S324
    sha1_algo.update(payload)
    return sha1_algo.hexdigest()


class AesTransport(BaseTransport):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT = 80
    SESSION_COOKIE_NAME = "TP_SESSIONID"
    COMMON_HEADERS = {
        "Content-Type": "application/json",
        "requestByApp": "true",
        "Accept": "application/json",
    }

    def __init__(
        self,
        *,
        cparams: ConnectionParameters,
    ) -> None:
        super().__init__(cparams=cparams)
        self._port = cparams.port or self.DEFAULT_PORT

        self._http_client: httpx.AsyncClient = (
            cparams.http_client or httpx.AsyncClient()
        )
        self._handshake_done = False

        self._encryption_session: Optional[AesEncyptionSession] = None
        self._session_expire_at: Optional[float] = None

        self._session_cookie = None

        self._login_token = None

        _LOGGER.debug("Created AES transport for %s", self._host)

    def hash_credentials(self, login_v2):
        """Hash the credentials."""
        if login_v2:
            un = base64.b64encode(
                _sha1(self._credentials.username.encode()).encode()
            ).decode()
            pw = base64.b64encode(
                _sha1(self._credentials.password.encode()).encode()
            ).decode()
        else:
            un = base64.b64encode(
                _sha1(self._credentials.username.encode()).encode()
            ).decode()
            pw = base64.b64encode(self._credentials.password.encode()).decode()
        return un, pw

    async def client_post(self, url, params=None, data=None, json=None, headers=None):
        """Send an http post request to the device."""
        response_data = None
        cookies = None
        if self._session_cookie:
            cookies = httpx.Cookies()
            cookies.set(self.SESSION_COOKIE_NAME, self._session_cookie)
        self._http_client.cookies.clear()
        resp = await self._http_client.post(
            url,
            params=params,
            data=data,
            json=json,
            timeout=self._timeout,
            cookies=cookies,
            headers=self.COMMON_HEADERS,
        )
        if resp.status_code == 200:
            response_data = resp.json()

        return resp.status_code, response_data

    def _handle_response_error_code(self, resp_dict: dict, msg: str):
        error_code = SmartErrorCode(resp_dict.get("error_code"))  # type: ignore[arg-type]
        if error_code == SmartErrorCode.SUCCESS:
            return
        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_TIMEOUT_ERRORS:
            raise TimeoutException(msg, error_code=error_code)
        if error_code in SMART_RETRYABLE_ERRORS:
            raise RetryableException(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._handshake_done = False
            self._login_token = None
            raise AuthenticationException(msg, error_code=error_code)
        raise SmartDeviceException(msg, error_code=error_code)

    async def send_secure_passthrough(self, request: str):
        """Send encrypted message as passthrough."""
        url = f"http://{self._host}/app"
        if self._login_token:
            url += f"?token={self._login_token}"

        encrypted_payload = self._encryption_session.encrypt(request.encode())  # type: ignore
        passthrough_request = {
            "method": "securePassthrough",
            "params": {"request": encrypted_payload.decode()},
        }
        status_code, resp_dict = await self.client_post(url, json=passthrough_request)
        # _LOGGER.debug(f"secure_passthrough response is {status_code}: {resp_dict}")

        if status_code != 200:
            raise SmartDeviceException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        response = self._encryption_session.decrypt(  # type: ignore
            resp_dict["result"]["response"].encode()
        )
        resp_dict = json_loads(response)
        return resp_dict

    async def _perform_login_for_version(self, *, login_version: int = 1):
        """Login to the device."""
        self._login_token = None
        un, pw = self.hash_credentials(login_version == 2)
        password_field_name = "password2" if login_version == 2 else "password"
        login_request = {
            "method": "login_device",
            "params": {password_field_name: pw, "username": un},
            "request_time_milis": round(time.time() * 1000),
        }
        request = json_dumps(login_request)
        try:
            resp_dict = await self.send_secure_passthrough(request)
        except SmartDeviceException as ex:
            raise AuthenticationException(ex) from ex
        self._login_token = resp_dict["result"]["token"]

    async def perform_login(self) -> None:
        """Login to the device."""
        try:
            await self._perform_login_for_version(login_version=2)
        except AuthenticationException:
            _LOGGER.warning("Login version 2 failed, trying version 1")
            await self.perform_handshake()
            await self._perform_login_for_version(login_version=1)

    async def perform_handshake(self):
        """Perform the handshake."""
        _LOGGER.debug("Will perform handshaking...")
        _LOGGER.debug("Generating keypair")

        self._handshake_done = False
        self._session_expire_at = None
        self._session_cookie = None

        url = f"http://{self._host}/app"
        key_pair = KeyPair.create_key_pair()

        pub_key = (
            "-----BEGIN PUBLIC KEY-----\n"
            + key_pair.get_public_key()
            + "\n-----END PUBLIC KEY-----\n"
        )
        handshake_params = {"key": pub_key}
        _LOGGER.debug(f"Handshake params: {handshake_params}")

        request_body = {"method": "handshake", "params": handshake_params}

        _LOGGER.debug(f"Request {request_body}")

        status_code, resp_dict = await self.client_post(url, json=request_body)

        _LOGGER.debug(f"Device responded with: {resp_dict}")

        if status_code != 200:
            raise SmartDeviceException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to handshake"
            )

        self._handle_response_error_code(resp_dict, "Unable to complete handshake")

        handshake_key = resp_dict["result"]["key"]

        self._session_cookie = self._http_client.cookies.get(  # type: ignore
            self.SESSION_COOKIE_NAME
        )
        if not self._session_cookie:
            self._session_cookie = self._http_client.cookies.get(  # type: ignore
                "SESSIONID"
            )

        self._session_expire_at = time.time() + 86400
        self._encryption_session = AesEncyptionSession.create_from_keypair(
            handshake_key, key_pair
        )

        self._handshake_done = True

        _LOGGER.debug("Handshake with %s complete", self._host)

    def _handshake_session_expired(self):
        """Return true if session has expired."""
        return (
            self._session_expire_at is None
            or self._session_expire_at - time.time() <= 0
        )

    async def send(self, request: str):
        """Send the request."""
        if not self._handshake_done or self._handshake_session_expired():
            await self.perform_handshake()
        if not self._login_token:
            await self.perform_login()

        return await self.send_secure_passthrough(request)

    async def close(self) -> None:
        """Close the protocol."""
        client = self._http_client
        self._http_client = None
        self._handshake_done = False
        self._login_token = None
        if client:
            await client.aclose()


class AesEncyptionSession:
    """Class for an AES encryption session."""

    @staticmethod
    def create_from_keypair(handshake_key: str, keypair):
        """Create the encryption session."""
        handshake_key_bytes: bytes = base64.b64decode(handshake_key.encode("UTF-8"))
        private_key_data = base64.b64decode(keypair.get_private_key().encode("UTF-8"))

        private_key = serialization.load_der_private_key(private_key_data, None, None)
        key_and_iv = private_key.decrypt(
            handshake_key_bytes, asymmetric_padding.PKCS1v15()
        )
        if key_and_iv is None:
            raise ValueError("Decryption failed!")

        return AesEncyptionSession(key_and_iv[:16], key_and_iv[16:])

    def __init__(self, key, iv):
        self.cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        self.padding_strategy = padding.PKCS7(algorithms.AES.block_size)

    def encrypt(self, data) -> bytes:
        """Encrypt the message."""
        encryptor = self.cipher.encryptor()
        padder = self.padding_strategy.padder()
        padded_data = padder.update(data) + padder.finalize()
        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return base64.b64encode(encrypted)

    def decrypt(self, data) -> str:
        """Decrypt the message."""
        decryptor = self.cipher.decryptor()
        unpadder = self.padding_strategy.unpadder()
        decrypted = decryptor.update(base64.b64decode(data)) + decryptor.finalize()
        unpadded_data = unpadder.update(decrypted) + unpadder.finalize()
        return unpadded_data.decode()


class KeyPair:
    """Class for generating key pairs."""

    @staticmethod
    def create_key_pair(key_size: int = 1024):
        """Create a key pair."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        public_key = private_key.public_key()

        private_key_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        return KeyPair(
            private_key=base64.b64encode(private_key_bytes).decode("UTF-8"),
            public_key=base64.b64encode(public_key_bytes).decode("UTF-8"),
        )

    def __init__(self, private_key: str, public_key: str):
        self.private_key = private_key
        self.public_key = public_key

    def get_private_key(self) -> str:
        """Get the private key."""
        return self.private_key

    def get_public_key(self) -> str:
        """Get the public key."""
        return self.public_key
