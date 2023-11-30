"""Implementation of the TP-Link AES Protocol.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

import asyncio
import base64
import hashlib
import logging
import time
import uuid
from pprint import pformat as pf
from typing import Dict, Optional, Union

import httpx
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .credentials import Credentials
from .exceptions import AuthenticationException, SmartDeviceException
from .json import dumps as json_dumps
from .json import loads as json_loads
from .protocol import TPLinkProtocol

_LOGGER = logging.getLogger(__name__)
logging.getLogger("httpx").propagate = False


def _md5(payload: bytes) -> bytes:
    digest = hashes.Hash(hashes.MD5())  # noqa: S303
    digest.update(payload)
    hash = digest.finalize()
    return hash


def _sha1(payload: bytes) -> str:
    sha1_algo = hashlib.sha1()  # noqa: S324
    sha1_algo.update(payload)
    return sha1_algo.hexdigest()


class TPLinkAes(TPLinkProtocol):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT = 80
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
        super().__init__(host=host, port=self.DEFAULT_PORT)

        self.credentials = (
            credentials
            if credentials and credentials.username and credentials.password
            else Credentials(username="", password="")
        )

        self._local_seed: Optional[bytes] = None
        self.local_auth_hash = self.generate_auth_hash(self.credentials)
        self.local_auth_owner = self.generate_owner_hash(self.credentials).hex()
        self.kasa_setup_auth_hash = None
        self.blank_auth_hash = None
        self.handshake_lock = asyncio.Lock()
        self.query_lock = asyncio.Lock()
        self.handshake_done = False

        self.encryption_session: Optional[AesEncyptionSession] = None
        self.session_expire_at: Optional[float] = None

        self.timeout = timeout if timeout else self.DEFAULT_TIMEOUT
        self.session_cookie = None
        self.terminal_uuid = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self.request_id_generator = SnowflakeId(1, 1)
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

    async def send_secure_passthrough(self, request):
        """Send encrypted message as passthrough."""
        url = f"http://{self.host}/app"
        if self.login_token:
            url += f"?token={self.login_token}"
        raw_request = json_dumps(request)
        encrypted_payload = self.encryption_session.encrypt(raw_request.encode())
        passthrough_request = {
            "method": "securePassthrough",
            "params": {"request": encrypted_payload.decode()},
        }
        status_code, resp_dict = await self.client_post(url, json=passthrough_request)
        if status_code == 200 and resp_dict["error_code"] == 0:
            response = self.encryption_session.decrypt(
                resp_dict["result"]["response"].encode()
            )
            resp_dict = json_loads(response)
            if resp_dict["error_code"] != 0:
                raise SmartDeviceException(
                    f"Could not complete send, response was {resp_dict}",
                )
            if "result" in resp_dict:
                return resp_dict["result"]
        else:
            raise AuthenticationException("Could not complete send")

    def get_aes_request(self, method, params=None):
        """Get a request message."""
        request = {
            "method": method,
            "params": params,
            "requestID": self.request_id_generator.generate_id(),
            "request_time_milis": round(time.time() * 1000),
            "terminal_uuid": self.terminal_uuid,
        }
        return request

    async def perform_login(self, login_v2):
        """Login to the device."""
        self.login_token = None

        un, pw = self.hash_credentials(self.credentials, login_v2)
        params = {"password": pw, "username": un}
        request = self.get_aes_request("login_device", params)
        try:
            result = await self.send_secure_passthrough(request)
        except SmartDeviceException as ex:
            raise AuthenticationException(ex) from ex
        self.login_token = result["token"]

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

            self.terminal_uuid = base64.b64encode(_md5(uuid.uuid4().bytes)).decode(
                "UTF-8"
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

    @staticmethod
    def generate_auth_hash(creds: Credentials):
        """Generate an md5 auth hash for the protocol on the supplied credentials."""
        un = creds.username or ""
        pw = creds.password or ""
        return _md5(_md5(un.encode()) + _md5(pw.encode()))

    @staticmethod
    def generate_owner_hash(creds: Credentials):
        """Return the MD5 hash of the username in this object."""
        un = creds.username or ""
        return _md5(un.encode())

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device retrying for retry_count on failure."""
        async with self.query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except httpx.CloseError as sdex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {sdex}"
                    ) from sdex
                continue
            except httpx.ConnectError as cex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}: {cex}"
                ) from cex
            except TimeoutError as tex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device, timed out: {self.host}: {tex}"
                ) from tex
            except AuthenticationException as auex:
                _LOGGER.debug("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    ) from ex
                continue

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: Union[str, Dict], retry_count: int) -> Dict:
        _LOGGER.debug(
            "%s >> %s",
            self.host,
            _LOGGER.isEnabledFor(logging.DEBUG) and pf(request),
        )

        if not self.http_client:
            self.http_client = httpx.AsyncClient()

        if not self.handshake_done or self.handshake_session_expired():
            try:
                await self.perform_handshake()
                await self.perform_login(False)
            except AuthenticationException:
                await self.perform_handshake()
                await self.perform_login(True)

        if isinstance(request, dict):
            aes_method = next(iter(request))
            aes_params = request[aes_method]
        else:
            aes_method = request
            aes_params = None

        aes_request = self.get_aes_request(aes_method, aes_params)
        response_data = await self.send_secure_passthrough(aes_request)

        _LOGGER.debug(
            "%s << %s",
            self.host,
            _LOGGER.isEnabledFor(logging.DEBUG) and pf(response_data),
        )

        return response_data

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


class SnowflakeId:
    """Class for generating snowflake ids."""

    EPOCH = 1420041600000  # Custom epoch (in milliseconds)
    WORKER_ID_BITS = 5
    DATA_CENTER_ID_BITS = 5
    SEQUENCE_BITS = 12

    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1
    MAX_DATA_CENTER_ID = (1 << DATA_CENTER_ID_BITS) - 1

    SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1

    def __init__(self, worker_id, data_center_id):
        if worker_id > SnowflakeId.MAX_WORKER_ID or worker_id < 0:
            raise ValueError(
                "Worker ID can't be greater than "
                + str(SnowflakeId.MAX_WORKER_ID)
                + " or less than 0"
            )
        if data_center_id > SnowflakeId.MAX_DATA_CENTER_ID or data_center_id < 0:
            raise ValueError(
                "Data center ID can't be greater than "
                + str(SnowflakeId.MAX_DATA_CENTER_ID)
                + " or less than 0"
            )

        self.worker_id = worker_id
        self.data_center_id = data_center_id
        self.sequence = 0
        self.last_timestamp = -1

    def generate_id(self):
        """Generate a snowflake id."""
        timestamp = self._current_millis()

        if timestamp < self.last_timestamp:
            raise ValueError("Clock moved backwards. Refusing to generate ID.")

        if timestamp == self.last_timestamp:
            # Within the same millisecond, increment the sequence number
            self.sequence = (self.sequence + 1) & SnowflakeId.SEQUENCE_MASK
            if self.sequence == 0:
                # Sequence exceeds its bit range, wait until the next millisecond
                timestamp = self._wait_next_millis(self.last_timestamp)
        else:
            # New millisecond, reset the sequence number
            self.sequence = 0

        # Update the last timestamp
        self.last_timestamp = timestamp

        # Generate and return the final ID
        return (
            (
                (timestamp - SnowflakeId.EPOCH)
                << (
                    SnowflakeId.WORKER_ID_BITS
                    + SnowflakeId.SEQUENCE_BITS
                    + SnowflakeId.DATA_CENTER_ID_BITS
                )
            )
            | (
                self.data_center_id
                << (SnowflakeId.SEQUENCE_BITS + SnowflakeId.WORKER_ID_BITS)
            )
            | (self.worker_id << SnowflakeId.SEQUENCE_BITS)
            | self.sequence
        )

    def _current_millis(self):
        return round(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp):
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp
