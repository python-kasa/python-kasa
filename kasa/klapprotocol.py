"""Implementation of the TP-Link Klap Home Protocol.

Comment by sdb - 4-Jul-2023

Encryption/Decryption methods based on the works of
Simon Wilkinson and Chris Weeldon

While working on these changes I discovered my HS100 devices
would periodically change their device owner to something
that produces the following
md5 owner hash: 994661e5222b8e5e3e1d90e73a322315.
It seems to be after an update to the on/off state
that was scheduled via the app.
Switching the device on and off manually via the
Kasa app would revert to the correct owner.

For devices that have not been connected to the kasa
cloud the theory is that blank username and password
md5 hashes will succesfully authenticate but
at this point I have been unable to verify.

https://gist.github.com/chriswheeldon/3b17d974db3817613c69191c0480fe55
https://github.com/python-kasa/python-kasa/pull/117

N.B. chrisweeldon implementation had a bug in the encryption
logic for determining the initial seq number and Simon Wilkinson's
implementation did not seem to support
incrementing the sequence number for subsequent encryption requests
"""
import asyncio
import datetime
import hashlib
import logging
import secrets
import time
from pprint import pformat as pf
from typing import Any, Dict, Optional, Tuple, Union

import aiohttp
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from yarl import URL

from .credentials import Credentials
from .exceptions import AuthenticationException, SmartDeviceException
from .json import dumps as json_dumps
from .json import loads as json_loads
from .protocol import TPLinkProtocol

_LOGGER = logging.getLogger(__name__)


class TPLinkKlap(TPLinkProtocol):
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, used by newer firmware versions.
    """

    DEFAULT_PORT = 80
    DISCOVERY_PORT = 20002
    DEFAULT_TIMEOUT = 5
    DISCOVERY_QUERY = {"system": {"get_sysinfo": None}}
    KASA_SETUP_EMAIL = "kasa@tp-link.net"
    KASA_SETUP_PASSWORD = "kasaSetup"  # noqa: S105

    def __init__(
        self,
        host: str,
        credentials: Optional[Credentials] = None,
        discovery_data: Optional[dict] = None,
    ) -> None:
        super().__init__(host=host, port=self.DEFAULT_PORT)

        self.credentials = (
            credentials
            if credentials and credentials.username and credentials.password
            else Credentials(username="", password="")
        )
        self.discovery_data = discovery_data if discovery_data is not None else {}
        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)

        self._local_seed: Optional[bytes] = None
        self.local_auth_hash = self.generate_auth_hash(self.credentials)
        self.local_auth_owner = self.generate_owner_hash(self.credentials).hex()
        self.handshake_lock = asyncio.Lock()
        self.query_lock = asyncio.Lock()
        self.handshake_done = False

        self.encryption_session: Optional[KlapEncryptionSession] = None
        self.session_expire_at: Optional[float] = None

        self.timeout = self.DEFAULT_TIMEOUT

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    @staticmethod
    def _sha256(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    @staticmethod
    def _md5(payload: bytes) -> bytes:
        digest = hashes.Hash(hashes.MD5())  # noqa: S303
        digest.update(payload)
        hash = digest.finalize()
        return hash

    @staticmethod
    async def session_post(session, url, params=None, data=None):
        """Send an http post request to the device."""
        response_data = None

        resp = await session.post(url, params=params, data=data)
        async with resp:
            if resp.status == 200:
                response_data = await resp.read()

        return resp.status, response_data

    @staticmethod
    def get_local_seed():
        """Get the local seed.  Can be mocked for testing."""
        return secrets.token_bytes(16)

    @staticmethod
    async def perform_handshake1(
        host, session, auth_hash
    ) -> Tuple[bytes, bytes, bytes]:
        """Perform handshake1."""
        local_seed = TPLinkKlap.get_local_seed()

        # Handshake 1 has a payload of local_seed
        # and a response of 16 bytes, followed by
        # sha256(clientBytes | authenticator)

        payload = local_seed

        url = f"http://{host}/app/handshake1"

        response_status, response_data = await TPLinkKlap.session_post(
            session, url, data=payload
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Handshake1 posted at %s. Host is %s, Response"
                + "status is %s, Request was %s",
                datetime.datetime.now(),
                host,
                response_status,
                payload and payload.hex(),
            )

        if response_status != 200:
            raise AuthenticationException(
                f"Device {host} responded with {response_status} to handshake1"
            )

        remote_seed = response_data[0:16]
        server_hash = response_data[16:]

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Handshake1 success at %s. Host is %s, "
                + "Server remote_seed is: %s, server hash is: %s",
                datetime.datetime.now(),
                host,
                remote_seed.hex(),
                server_hash.hex(),
            )

        local_seed_auth_hash = TPLinkKlap._sha256(local_seed + auth_hash)

        # Check the response from the device
        if local_seed_auth_hash == server_hash:
            _LOGGER.debug("handshake1 hashes match")
            return local_seed, remote_seed, auth_hash
        else:
            _LOGGER.debug(
                "Expected %s got %s in handshake1.  Checking if blank auth is a match",
                local_seed_auth_hash.hex(),
                server_hash.hex(),
            )

            blank_auth = Credentials(username="", password="")
            blank_auth_hash = TPLinkKlap.generate_auth_hash(blank_auth)
            blank_seed_auth_hash = TPLinkKlap._sha256(local_seed + blank_auth_hash)
            if blank_seed_auth_hash == server_hash:
                _LOGGER.debug(
                    "Server response doesn't match our expected hash on ip %s"
                    + " but an authentication with blank credentials matched",
                    host,
                )
                return local_seed, remote_seed, blank_auth_hash
            else:
                kasa_setup_auth = Credentials(
                    username=TPLinkKlap.KASA_SETUP_EMAIL,
                    password=TPLinkKlap.KASA_SETUP_PASSWORD,
                )
                kasa_setup_auth_hash = TPLinkKlap.generate_auth_hash(kasa_setup_auth)
                kasa_setup_seed_auth_hash = TPLinkKlap._sha256(
                    local_seed + kasa_setup_auth_hash
                )
                if kasa_setup_seed_auth_hash == server_hash:
                    auth_hash = kasa_setup_auth_hash
                    _LOGGER.debug(
                        "Server response doesn't match our expected hash on ip %s"
                        + " but an authentication with kasa setup credentials matched",
                        host,
                    )
                    return local_seed, remote_seed, kasa_setup_auth_hash
                else:
                    msg = f"Server response doesn't match our challenge on ip {host}"
                    _LOGGER.debug(msg)
                    raise AuthenticationException(msg)

    @staticmethod
    async def perform_handshake2(
        host, session, local_seed, remote_seed, auth_hash
    ) -> "KlapEncryptionSession":
        """Perform handshake2."""
        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)

        url = f"http://{host}/app/handshake2"

        payload = TPLinkKlap._sha256(remote_seed + auth_hash)

        response_status, response_data = await TPLinkKlap.session_post(
            session, url, data=payload
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Handshake2 posted %s.  Host is %s, Response status is %s, "
                + "Request was %s",
                datetime.datetime.now(),
                host,
                response_status,
                payload.hex(),
            )

        if response_status != 200:
            raise AuthenticationException(
                f"Device {host} responded with {response_status} to handshake2"
            )
        else:
            return KlapEncryptionSession(local_seed, remote_seed, auth_hash)

    async def perform_handshake(self, session) -> Any:
        """Perform handshake1 and handshake2.

        Sets the encryption_session if successful.
        """
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)
        self.authentication_failed = False
        self.handshake_done = False
        self.session_expire_at = None

        session.cookie_jar.clear()

        local_seed, remote_seed, auth_hash = await self.perform_handshake1(
            self.host, session, self.local_auth_hash
        )

        # The evice returns a TIMEOUT cookie on handshake1 which
        # it doesn't like to get back
        url = f"http://{self.host}/app"
        session_cookie = session.cookie_jar.filter_cookies(url).get("TP_SESSIONID")
        session_timeout = session.cookie_jar.filter_cookies(url).get("TIMEOUT")
        session.cookie_jar.clear()
        session.cookie_jar.update_cookies({"TP_SESSIONID": session_cookie}, URL(url))
        self.session_expire_at = time.time() + int(
            session_timeout.value if session_timeout else 86400
        )

        self.encryption_session = await self.perform_handshake2(
            self.host, session, local_seed, remote_seed, auth_hash
        )
        self.handshake_done = True

        _LOGGER.debug("[KLAP] Handshake with %s complete", self.host)

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
        return TPLinkKlap._md5(
            TPLinkKlap._md5(un.encode()) + TPLinkKlap._md5(pw.encode())
        )

    @staticmethod
    def generate_owner_hash(creds: Credentials):
        """Return the MD5 hash of the username in this object."""
        un = creds.username or ""
        return TPLinkKlap._md5(un.encode())

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device retrying for retry_count on failure."""
        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)  # noqa: S101

        async with self.query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: str, retry_count: int = 3) -> Dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except aiohttp.ServerDisconnectedError as sdex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {sdex}"
                    ) from sdex
                continue
            except aiohttp.ClientConnectionError as cex:
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}: {cex}"
                ) from cex
            except TimeoutError as tex:
                raise SmartDeviceException(
                    f"Unable to connect to the device, timed out: {self.host}: {tex}"
                ) from tex
            except AuthenticationException as auex:
                _LOGGER.debug("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    ) from ex
                continue

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: str, retry_count: int) -> Dict:
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(
            cookie_jar=self.jar, timeout=timeout
        ) as session:
            if not self.handshake_done or self.handshake_session_expired():
                try:
                    await self.perform_handshake(session)

                except AuthenticationException as auex:
                    _LOGGER.debug(
                        "Unable to complete handshake for device %s, "
                        + "authentication failed",
                        self.host,
                    )
                    self.authentication_failed = True
                    raise auex

            # Check for mypy
            if self.encryption_session is not None:
                payload, seq = self.encryption_session.encrypt(request.encode())

            url = f"http://{self.host}/app/request"

            response_status, response_data = await self.session_post(
                session, url, params={"seq": seq}, data=payload
            )

            msg = (
                f"at {datetime.datetime.now()}.  Host is {self.host}, "
                + "Retry count is {retry_count}, Sequence is {seq}, "
                + "Response status is {response_status}, Request was {request}"
            )
            if response_status != 200:
                _LOGGER.error("Query failed after succesful authentication " + msg)
                # If we failed with a security error, force a new handshake next time.
                if response_status == 403:
                    self.handshake_done = False
                    self.authentication_failed = True
                    raise AuthenticationException(
                        f"Got a security error from {self.host} after handshake "
                        + "completed {self.discovery_data}"
                    )
                else:
                    raise SmartDeviceException(
                        f"Device {self.host} responded with {response_status} to"
                        + "request with seq {seq}"
                    )
            else:
                _LOGGER.debug("Query posted " + msg)

                self.authentication_failed = False

                # Check for mypy
                if self.encryption_session is not None:
                    decrypted_response = self.encryption_session.decrypt(response_data)

                json_payload = json_loads(decrypted_response)

                _LOGGER.debug(
                    "%s << %s",
                    self.host,
                    _LOGGER.isEnabledFor(logging.DEBUG) and pf(json_payload),
                )

                return json_payload

    async def close(self) -> None:
        """Close the protocol.  Does nothing for this implementation."""


class KlapEncryptionSession:
    """Class to represent an encryption session and it's internal state.

    i.e. sequence number which the device expects to increment.
    """

    def __init__(self, local_seed, remote_seed, user_hash):
        self.local_seed = local_seed
        self.remote_seed = remote_seed
        self.user_hash = user_hash
        self._key = self._key_derive(local_seed, remote_seed, user_hash)
        (self._iv, self._seq) = self._iv_derive(local_seed, remote_seed, user_hash)
        self._sig = self._sig_derive(local_seed, remote_seed, user_hash)

    def _key_derive(self, local_seed, remote_seed, user_hash):
        payload = b"lsk" + local_seed + remote_seed + user_hash
        return hashlib.sha256(payload).digest()[:16]

    def _iv_derive(self, local_seed, remote_seed, user_hash):
        # iv is first 16 bytes of sha256, where the last 4 bytes forms the
        # sequence number used in requests and is incremented on each request
        payload = b"iv" + local_seed + remote_seed + user_hash
        fulliv = hashlib.sha256(payload).digest()
        seq = int.from_bytes(fulliv[-4:], "big", signed=True)
        return (fulliv[:12], seq)

    def _sig_derive(self, local_seed, remote_seed, user_hash):
        # used to create a hash with which to prefix each request
        payload = b"ldk" + local_seed + remote_seed + user_hash
        return hashlib.sha256(payload).digest()[:28]

    def _iv_seq(self):
        seq = self._seq.to_bytes(4, "big", signed=True)
        iv = self._iv + seq
        return iv

    def encrypt(self, msg):
        """Encrypt the data and increment the sequence number."""
        self._seq = self._seq + 1
        if isinstance(msg, str):
            msg = msg.encode("utf-8")

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv_seq()))
        encryptor = cipher.encryptor()
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(msg) + padder.finalize()
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        digest = hashes.Hash(hashes.SHA256())
        digest.update(
            self._sig + self._seq.to_bytes(4, "big", signed=True) + ciphertext
        )
        signature = digest.finalize()

        return (signature + ciphertext, self._seq)

    def decrypt(self, msg):
        """Decrypt the data."""
        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv_seq()))
        decryptor = cipher.decryptor()
        dp = decryptor.update(msg[32:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintextbytes = unpadder.update(dp) + unpadder.finalize()

        return plaintextbytes.decode()
