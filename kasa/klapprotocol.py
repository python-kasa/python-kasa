"""Implementation of the TP-Link Smart Home Protocol.

Comment by sdb - 4-Jul-2023

Encryption/Decryption methods based on the works of
Simon Wilkinson and Chris Weeldon

While working on these changes I discovered my HS100 devices would periodically change their device owner to something that produces the following
md5 owner hash: 994661e5222b8e5e3e1d90e73a322315.  It seems to be after an update to the on/off state that was scheduled via the app.  Switching the device on and off manually via the
Kasa app would revert to the correct owner.

For devices that have not been connected to the kasa cloud the theory is that blank username and password md5 hashes will succesfully authenticate but
at this point I have been unable to verify.

https://gist.github.com/chriswheeldon/3b17d974db3817613c69191c0480fe55
https://github.com/python-kasa/python-kasa/pull/117

N.B. chrisweeldon implementation had a bug in the encryption logic for determining the initial seq number and Simon Wilkinson's implementation did not seem to support
incrementing the sequence number for subsequent encryption requests

"""
import asyncio
import datetime
import hashlib
import logging
import secrets
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
    TP_SESSION_COOKIE_NAME = "TP_SESSIONID"
    KASA_SETUP_EMAIL = "kasa@tp-link.net"
    KASA_SETUP_PASSWORD = "kasaSetup"

    def __init__(
        self, host: str, credentials: Credentials = Credentials()
    ) -> None:
        super().__init__(host=host, port=self.DEFAULT_PORT)

        self.credentials = credentials if credentials.username is not None and credentials.password is not None else Credentials(username="",password="")
        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)

        self._local_seed: Optional[bytes] = None
        self.local_auth_hash = self.generate_auth_hash(self.credentials)
        self.local_auth_owner = self.generate_owner_hash(self.credentials).hex()
        self.handshake_lock = asyncio.Lock()
        self.query_lock = asyncio.Lock()
        self.handshake_done = False

        self.encryption_session: Optional[KlapEncryptionSession] = None

        self.timeout = self.DEFAULT_TIMEOUT

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    async def get_sysinfo_info(self):
        """Return discovery info from host or None if unable to."""
        return await self.query(TPLinkKlap.DISCOVERY_QUERY)

    @staticmethod
    def _sha256(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    @staticmethod
    def _md5(payload: bytes) -> bytes:
        digest = hashes.Hash(hashes.MD5())
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
            else:
                try:
                    response_data = await resp.read()
                except Exception:
                    pass

        return resp.status, response_data

    def get_local_seed(self):
        """Get the local seed.  Can be mocked for testing."""
        return secrets.token_bytes(16)

    @staticmethod
    def handle_cookies(session, url):
        """Strip out any cookies other than TP_SESSION."""
        # We need to include only the TP_SESSIONID cookie - the klap device sends a
        # TIMEOUT cookie after handshake1 that it doesn't like getting back again
        cookie = session.cookie_jar.filter_cookies(url).get(
            TPLinkKlap.TP_SESSION_COOKIE_NAME
        )
        session.cookie_jar.clear()
        session.cookie_jar.update_cookies(
            {TPLinkKlap.TP_SESSION_COOKIE_NAME: cookie}, URL(url)
        )

    def clear_cookies(self, session):
        """Clear out all cookies for new handshake."""
        session.cookie_jar.clear()
        self.jar.clear()

    async def perform_handshake1(
        self, session, new_local_seed: Optional[bytes] = None
    ) -> Tuple[bytes, bytes]:
        """Perform handshake1.  Resets authentication_failed to False at the start."""
        self.authentication_failed = False

        self.clear_cookies(session)

        if new_local_seed is not None:
            self._local_seed = new_local_seed
        else:
            self._local_seed = self.get_local_seed()

        # Handshake 1 has a payload of local_seed
        # and a response of 16 bytes, followed by sha256(clientBytes | authenticator)
        self.handshake_done = False

        payload = self._local_seed

        url = f"http://{self.host}/app/handshake1"

        response_status, response_data = await self.session_post(
            session, url, data=payload
        )

        cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)

        if response_status != 200:
            raise AuthenticationException(
                "Device %s responded with %d to handshake1, this is probably not a klap device"
                % (self.host, response_status)
            )
        self.handle_cookies(session, url)

        remote_seed = response_data[0:16]
        server_hash = response_data[16:]

        cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)
        _LOGGER.debug(
            f"Handshake1 posted at {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Response status is {response_status}, Request was {self.local_auth_hash.hex()}"
        )

        _LOGGER.debug(
            "Server remote_seed is: %s, server hash is: %s",
            remote_seed.hex(),
            server_hash.hex(),
        )

        local_seed_auth_hash = self._sha256(self._local_seed + self.local_auth_hash)

        # Check the response from the device
        if local_seed_auth_hash == server_hash:
            _LOGGER.debug("handshake1 hashes match")
            return remote_seed, self.local_auth_hash
        else:
            _LOGGER.debug(
                "Expected %s got %s in handshake1.  Checking if blank auth is a match",
                local_seed_auth_hash.hex(),
                server_hash.hex(),
            )

            blank_auth = Credentials(username="", password="")
            blank_auth_hash = self.generate_auth_hash(blank_auth)
            blank_seed_auth_hash = self._sha256(self._local_seed + blank_auth_hash)
            if blank_seed_auth_hash == server_hash:
                _LOGGER.debug(
                    "Server response doesn't match our expected hash on ip %s but an authentication with blank credentials matched",
                    self.host,
                )
                return remote_seed, blank_auth_hash
            else:
                kasa_setup_auth = Credentials(
                    username=self.KASA_SETUP_EMAIL, password=self.KASA_SETUP_PASSWORD
                )
                kasa_setup_auth_hash = self.generate_auth_hash(kasa_setup_auth)
                kasa_setup_seed_auth_hash = self._sha256(
                    self._local_seed + kasa_setup_auth_hash
                )
                if kasa_setup_seed_auth_hash == server_hash:
                    self.local_auth_hash = kasa_setup_auth_hash
                    _LOGGER.debug(
                        "Server response doesn't match our expected hash on ip %s but an authentication with kasa setup credentials matched",
                        self.host,
                    )
                    return remote_seed, kasa_setup_auth_hash
                else:
                    self.authentication_failed = True
                    msg = "Server response doesn't match our challenge on ip {}".format(
                        self.host
                    )
                    _LOGGER.debug(msg)
                    raise AuthenticationException(msg)

    async def perform_handshake2(self, session, remote_seed, auth_hash) -> None:
        """Perform handshake2.  Sets authentication_failed based on success/failure."""
        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)

        url = f"http://{self.host}/app/handshake2"

        payload = self._sha256(remote_seed + auth_hash)

        response_status, response_data = await self.session_post(
            session, url, data=payload
        )

        cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)
        _LOGGER.debug(
            f"Handshake2 posted {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Response status is {response_status}, Request was {payload!r}"
        )

        if response_status != 200:
            self.authentication_failed = True
            self.handshake_done = False
            raise AuthenticationException(
                "Device responded with %d to handshake2" % response_status
            )
        else:
            self.authentication_failed = False
            self.handshake_done = True
            self.handle_cookies(session, url)

    async def perform_handshake(
        self, session, new_local_seed: Optional[bytes] = None
    ) -> Any:
        """Perform handshake1 and handshake2 and set the encryption_session if successful."""
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        remote_seed, auth_hash = await self.perform_handshake1(session, new_local_seed)

        await self.perform_handshake2(session, remote_seed, auth_hash)

        self.encryption_session = KlapEncryptionSession(
            self._local_seed, remote_seed, auth_hash
        )

        _LOGGER.debug("[KLAP] Handshake with %s complete", self.host)

    @staticmethod
    def generate_auth_hash(auth: Credentials):
        """Generate an md5 auth hash for the protocol on the supplied credentials."""
        return TPLinkKlap._md5(
            TPLinkKlap._md5(auth.username.encode())
            + TPLinkKlap._md5(auth.password.encode())
        )

    @staticmethod
    def generate_owner_hash(auth: Credentials):
        """Return the MD5 hash of the username in this object."""
        return TPLinkKlap._md5(auth.username.encode())

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device retrying for retry_count on failure."""
        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)

        async with self.query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: str, retry_count: int = 3) -> Dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except aiohttp.ClientConnectionError as ex:
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}: {ex}"
                )
            except TimeoutError as ex:
                raise SmartDeviceException(
                    f"Unable to connect to the device, timed out: {self.host}: {ex}"
                )
            except AuthenticationException as auex:
                _LOGGER.debug("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    )
                continue

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: str, retry_count: int) -> Dict:
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(
            cookie_jar=self.jar, timeout=timeout
        ) as session:
            if not self.handshake_done:
                try:
                    await self.perform_handshake(session)

                except AuthenticationException as auex:
                    _LOGGER.debug(
                        f"Unable to complete handshake for device {self.host}, authentication failed"
                    )
                    raise auex

            # Check for mypy
            if self.encryption_session is not None:
                payload, seq = self.encryption_session.encrypt(request.encode())

            url = f"http://{self.host}/app/request"

            cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)

            response_status, response_data = await self.session_post(
                session, url, params={"seq": seq}, data=payload
            )

            if response_status != 200:
                _LOGGER.error(
                    f"Query failed after succesful authentication at {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Retry count is {retry_count}, Sequence is {seq}, Response status is {response_status}, Request was {request}"
                )
                # If we failed with a security error, force a new handshake next time.
                if response_status == 403:
                    self.handshake_done = False
                    self.authentication_failed = True
                    raise AuthenticationException(
                        "Got a security error after handshake completed"
                    )
                else:
                    raise SmartDeviceException(
                        "Device %s responded with %d to request with seq %d"
                        % (self.host, response_status, seq)
                    )
            else:
                _LOGGER.debug(
                    f"Query posted at {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Retry count is {retry_count}, Sequence is {seq}, Response status is {response_status}, Request was {request}"
                )

                self.handle_cookies(session, url)

                self.authentication_failed = False

                # Check for mypy
                if self.encryption_session is not None:
                    decrypted_response = self.encryption_session.decrypt(response_data)

                json_payload = json_loads(decrypted_response)

                _LOGGER.debug("%s << %s", self.host, pf(json_payload))

                return json_payload

    async def close(self) -> None:
        """Close the protocol.  Does nothing for this implementation."""
        pass

    def parse_unauthenticated_info(self, unauthenticated_info) -> Dict[str, str]:
        """Parse raw unauthenticated info based on the data the protocol expects."""
        if "result" not in unauthenticated_info:
            raise SmartDeviceException(
                f"Received unexpected unauthenticated_info for {self.host}"
            )

        result = unauthenticated_info["result"]

        if unauthenticated_info["result"]["owner"] != self.local_auth_owner:
            pad = 8 + len("python-kasa.tplinkklap.auth_message") + 2
            msg = "The owner hashes do not match, if you expected authentication\n"
            msg += f"{' ':>{pad}}to work try switching the device on and off via the Kasa app\n"
            msg += f"{' ':>{pad}}to see if the device owner gets corrected."
        else:
            msg = "The owner hashed match, do you have the wrong password?"

        def _get_value(thedict, value):
            return "" if thedict == "" or value not in thedict else thedict[value]

        return {
            "ip": _get_value(result, "ip"),
            "mac": _get_value(result, "mac"),
            "device_id": _get_value(result, "device_id"),
            "owner": _get_value(result, "owner"),
            "device_type": _get_value(result, "device_type"),
            "device_model": _get_value(result, "device_model"),
            "hw_ver": _get_value(result, "hw_ver"),
            "factory_default": _get_value(result, "factory_default"),
            "mgt_encrypt_schm.is_support_https": _get_value(
                _get_value(result, "mgt_encrypt_schm"), "is_support_https"
            ),
            "mgt_encrypt_schm.encrypt_type": _get_value(
                _get_value(result, "mgt_encrypt_schm"), "encrypt_type"
            ),
            "mgt_encrypt_schm.http_port": _get_value(
                _get_value(result, "mgt_encrypt_schm"), "http_port"
            ),
            "error_code": _get_value(unauthenticated_info, "error_code"),
            "python-kasa.tplinkklap.auth_owner_hash": self.local_auth_owner,
            "python-kasa.tplinkklap.auth_message": msg,
        }


class KlapEncryptionSession:
    """Class to represent an encryption session and it's internal state, i.e. sequence number."""

    def __init__(self, local_seed, remote_seed, user_hash):
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
        assert len(iv) == 16
        return iv

    def encrypt(self, msg):
        """Encrypt the data and increment the sequence number."""
        self._seq = self._seq + 1
        if type(msg) == str:
            msg = msg.encode("utf-8")
        assert type(msg) == bytes

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
        assert type(msg) == bytes

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv_seq()))
        decryptor = cipher.decryptor()
        dp = decryptor.update(msg[32:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintextbytes = unpadder.update(dp) + unpadder.finalize()

        return plaintextbytes.decode()
