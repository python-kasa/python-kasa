"""Implementation of the TP-Link AES transport.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

import asyncio
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

from .credentials import Credentials
from .exceptions import AuthenticationException, SmartDeviceException
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

    DEFAULT_TIMEOUT = 5
    SESSION_COOKIE_NAME = "TP_SESSIONID"
    COMMON_HEADERS = {
        "Content-Type": "application/json",
        "requestByApp": "true",
        "Accept": "application/json",
    }

    def __init__(
        self,
        host: str,
        *,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host=host)

        self.credentials = (
            credentials
            if credentials and credentials.username and credentials.password
            else Credentials(username="", password="")
        )

        self._local_seed: Optional[bytes] = None
        self.kasa_setup_auth_hash = None
        self.blank_auth_hash = None
        self.handshake_lock = asyncio.Lock()

        self.handshake_done = False

        self.encryption_session: Optional[AesEncyptionSession] = None
        self.session_expire_at: Optional[float] = None

        self.timeout = timeout if timeout else self.DEFAULT_TIMEOUT
        self.session_cookie = None

        self.http_client: httpx.AsyncClient = httpx.AsyncClient()
        self.login_token = None

        _LOGGER.debug("Created AES object for %s", self.host)

    def hash_credentials(self, credentials, try_login_version2):
        """Hash the credentials."""
        if try_login_version2:
            un = base64.b64encode(
                _sha1(credentials.username.encode()).encode()
            ).decode()
            pw = base64.b64encode(
                _sha1(credentials.password.encode()).encode()
            ).decode()
        else:
            un = base64.b64encode(
                _sha1(credentials.username.encode()).encode()
            ).decode()
            pw = base64.b64encode(credentials.password.encode()).decode()
        return un, pw

    async def client_post(self, url, params=None, data=None, json=None, headers=None):
        """Send an http post request to the device."""
        response_data = None
        cookies = None
        if self.session_cookie:
            cookies = httpx.Cookies()
            cookies.set(self.SESSION_COOKIE_NAME, self.session_cookie)
        self.http_client.cookies.clear()
        resp = await self.http_client.post(
            url,
            params=params,
            data=data,
            json=json,
            timeout=self.timeout,
            cookies=cookies,
            headers=self.COMMON_HEADERS,
        )
        if resp.status_code == 200:
            response_data = resp.json()

        return resp.status_code, response_data

    async def send_secure_passthrough(self, request: str):
        """Send encrypted message as passthrough."""
        url = f"http://{self.host}/app"
        if self.login_token:
            url += f"?token={self.login_token}"

        encrypted_payload = self.encryption_session.encrypt(request.encode())  # type: ignore
        passthrough_request = {
            "method": "securePassthrough",
            "params": {"request": encrypted_payload.decode()},
        }
        status_code, resp_dict = await self.client_post(url, json=passthrough_request)
        _LOGGER.debug(f"secure_passthrough response is {status_code}: {resp_dict}")
        if status_code == 200 and resp_dict["error_code"] == 0:
            response = self.encryption_session.decrypt(  # type: ignore
                resp_dict["result"]["response"].encode()
            )
            _LOGGER.debug(f"decrypted secure_passthrough response is {response}")
            resp_dict = json_loads(response)
            return resp_dict
        else:
            self.handshake_done = False
            self.login_token = None
            raise AuthenticationException("Could not complete send")

    async def perform_login(self, login_request, login_v2):
        """Login to the device."""
        self.login_token = None

        if isinstance(login_request, str):
            login_request = json_loads(login_request)

        un, pw = self.hash_credentials(self.credentials, login_v2)
        login_request["params"] = {"password": pw, "username": un}
        request = json_dumps(login_request)
        try:
            resp_dict = await self.send_secure_passthrough(request)
        except SmartDeviceException as ex:
            raise AuthenticationException(ex) from ex
        self.login_token = resp_dict["result"]["token"]

    def needs_login(self) -> bool:
        """Return true if the transport needs to do a login."""
        return self.login_token is None

    async def login(self, request: str) -> None:
        """Login to the device."""
        try:
            if self.needs_handshake():
                raise SmartDeviceException(
                    "Handshake must be complete before trying to login"
                )
            await self.perform_login(request, False)
        except AuthenticationException:
            await self.perform_handshake()
            await self.perform_login(request, True)

    def needs_handshake(self) -> bool:
        """Return true if the transport needs to do a handshake."""
        return not self.handshake_done or self.handshake_session_expired()

    async def handshake(self) -> None:
        """Perform the encryption handshake."""
        await self.perform_handshake()

    async def perform_handshake(self):
        """Perform the handshake."""
        _LOGGER.debug("Will perform handshaking...")
        _LOGGER.debug("Generating keypair")

        self.handshake_done = False
        self.session_expire_at = None
        self.session_cookie = None

        url = f"http://{self.host}/app"
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

        if status_code == 200 and resp_dict["error_code"] == 0:
            _LOGGER.debug("Decoding handshake key...")
            handshake_key = resp_dict["result"]["key"]

            self.session_cookie = self.http_client.cookies.get(  # type: ignore
                self.SESSION_COOKIE_NAME
            )
            if not self.session_cookie:
                self.session_cookie = self.http_client.cookies.get(  # type: ignore
                    "SESSIONID"
                )

            self.session_expire_at = time.time() + 86400
            self.encryption_session = AesEncyptionSession.create_from_keypair(
                handshake_key, key_pair
            )

            self.handshake_done = True

            _LOGGER.debug("Handshake with %s complete", self.host)

        else:
            raise AuthenticationException("Could not complete handshake")

    def handshake_session_expired(self):
        """Return true if session has expired."""
        return (
            self.session_expire_at is None or self.session_expire_at - time.time() <= 0
        )

    async def send(self, request: str):
        """Send the request."""
        if self.needs_handshake():
            raise SmartDeviceException(
                "Handshake must be complete before trying to send"
            )
        if self.needs_login():
            raise SmartDeviceException("Login must be complete before trying to send")

        resp_dict = await self.send_secure_passthrough(request)
        if resp_dict["error_code"] != 0:
            self.handshake_done = False
            self.login_token = None
            raise SmartDeviceException(
                f"Could not complete send, response was {resp_dict}",
            )
        return resp_dict

    async def close(self) -> None:
        """Close the protocol."""
        client = self.http_client
        self.http_client = None
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
