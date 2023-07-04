"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

#994661e5222b8e5e3e1d90e73a322315

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import hashlib
import logging
import secrets
import binascii

# pycryptodome
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Util import Counter, Padding

import aiohttp

from yarl import URL

# from yarl import URL
from typing import Dict

from .auth import AuthCredentials, TPLinkAuthProtocol
from .exceptions import SmartDeviceException, SmartDeviceAuthenticationException
from typing import Any, Dict, List, Optional, Set, Union
from .json import dumps as json_dumps
from .json import loads as json_loads
from pprint import pformat as pf
import datetime

_LOGGER = logging.getLogger(__name__)


class TPLinkKlap(TPLinkAuthProtocol):
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, used by newer firmware versions.
    """

    DEFAULT_PORT = 80
    DISCOVERY_PORT = 20002
    DISCOVERY_TARGET = ("255,255,255,255", DISCOVERY_PORT)
    DISCOVERY_BROADCAST_PAYLOAD = binascii.unhexlify("020000010000000000000000463cb5d3")
    DISCOVERY_QUERY = {"system": {"get_sysinfo": None}}
    TP_SESSION_COOKIE_NAME = "TP_SESSIONID"

    def __init__(
        self, host: str, auth_credentials: AuthCredentials = AuthCredentials()
    ) -> None:
        super().__init__(
            host=host, port=self.DEFAULT_PORT, auth_credentials=auth_credentials
        )

        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)

        self._local_seed = None
        self.local_auth_hash = self.generate_auth_hash(self.auth_credentials)
        self.local_auth_owner = self.generate_owner_hash(self.auth_credentials).hex()
        self.handshake_lock = asyncio.Lock()
        self.query_lock = asyncio.Lock()
        self.handshake_done = False

        self.encryption_session = None

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    @staticmethod
    def get_discovery_targets(targetip: str = "255.255.255.255"):
        return [(targetip, TPLinkKlap.DISCOVERY_PORT)]

    @staticmethod
    def get_discovery_payload():
        return TPLinkKlap.DISCOVERY_BROADCAST_PAYLOAD

    @staticmethod
    def is_discovery_response_for_this_protocol(port, info):
        return port == TPLinkKlap.DISCOVERY_PORT

    def try_get_discovery_info(port, data):
        """Returns discovery info if the ports match and we can read the data"""
        # Depending on any future protocol changes the port check could be relaxed
        if port == TPLinkKlap.DISCOVERY_PORT:
            try:
                unauthenticated_info = json_loads(data[16:])
            except Exception as ex:
                return None

            isklap = (
                "result" in unauthenticated_info
                and "mgt_encrypt_schm" in unauthenticated_info["result"]
                and "encrypt_type" in unauthenticated_info["result"]["mgt_encrypt_schm"]
                and unauthenticated_info["result"]["mgt_encrypt_schm"]["encrypt_type"]
                == "KLAP"
            )
            if isklap:
                return unauthenticated_info
            else:
                return None
        else:
            return None

    async def try_query_discovery_info(self):
        """Returns discovery info from host"""
        try:
            info = await self.query(TPLinkKlap.DISCOVERY_QUERY)
            return info
        except SmartDeviceAuthenticationException as auex:
            _LOGGER.debug(
                "Unable to authenticate discovery for %s with TPLinkKLAP", self.host
            )
            return None
        except SmartDeviceException as sde:
            _LOGGER.debug("Unable to query discovery for %s with TPLinkKLAP", self.host)
            return None

    @staticmethod
    def _sha256(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    @staticmethod
    def _md5(payload: bytes) -> bytes:
        return hashlib.md5(payload).digest()

    @staticmethod
    async def session_post(session, url, params=None, data=None):
        response_data = None

        resp = await session.post(url, params=params, data=data)
        async with resp:
            if resp.status == 200:
                response_data = await resp.read()
            else:
                try:
                    response_data = await resp.read()
                except:
                    pass

        return resp.status, response_data

    def get_local_seed(self):
        return Random.get_random_bytes(16)

    @staticmethod
    def handle_cookies(session, url):
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
        session.cookie_jar.clear()
        self.jar.clear()

    async def perform_handshake1(self, session, new_local_seed: bytes = None) -> None:
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
            raise SmartDeviceAuthenticationException(
                "Device %s responded with %d to handshake1, this is probably not a klap device"
                % (self.host, response_status)
            )
        self.handle_cookies(session, url)

        self.remote_seed = response_data[0:16]
        server_hash = response_data[16:]

        cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)
        _LOGGER.debug(
            f"Handshake1 posted at {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Response status is {response_status}, Request was {self.local_auth_hash.hex()}"
        )

        _LOGGER.debug(
            "Server remote_seed is: %s, server hash is: %s",
            self.remote_seed.hex(),
            server_hash.hex(),
        )

        local_hash = self._sha256(self._local_seed + self.local_auth_hash)

        # Check the response from the device
        if local_hash != server_hash:
            _LOGGER.debug(
                "Expected %s got %s in handshake1.  Checking if blank auth is a match",
                local_hash.hex(),
                server_hash.hex(),
            )

            blank_auth = AuthCredentials()
            blank_auth_hash = self._sha256(
                self._local_seed + self.generate_auth_hash(blank_auth)
            )
            if blank_auth_hash == server_hash:
                self.auth_credentials = blank_auth
                self.local_auth_hash = blank_auth_hash
                _LOGGER.warn(
                    "Server response doesn't match our challenge on ip %s but an authentication with blank credentials matched",
                    self.host,
                )
            else:
                self.authentication_failed = True
                msg = "Server response doesn't match our challenge on ip {}".format(
                    self.host
                )
                _LOGGER.debug(msg)
                raise SmartDeviceAuthenticationException(msg)
        else:
            _LOGGER.debug("handshake1 hashes match")

    async def perform_handshake2(self, session) -> None:
        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)

        url = f"http://{self.host}/app/handshake2"

        payload = self._sha256(self.remote_seed + self.local_auth_hash)

        response_status, response_data = await self.session_post(
            session, url, data=payload
        )

        cookie = self.jar.filter_cookies(url).get(self.TP_SESSION_COOKIE_NAME)
        _LOGGER.debug(
            f"Handshake2 posted {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Response status is {response_status}, Request was {self.local_auth_hash}"
        )

        if response_status != 200:
            self.authentication_failed = True
            self.handshake_done = False
            raise SmartDeviceAuthenticationException(
                "Device responded with %d to handshake2" % response_status
            )
        else:
            self.authentication_failed = False
            self.handshake_done = True
            self.handle_cookies(session, url)

    async def perform_handshake(self, session, new_local_seed: bytes = None) -> Any:
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        await self.perform_handshake1(session, new_local_seed)

        await self.perform_handshake2(session)

        self.encryption_session = KlapEncryptionSession(
            self._local_seed, self.remote_seed, self.local_auth_hash
        )

        _LOGGER.debug("[KLAP] Handshake with %s complete", self.host)

    @staticmethod
    def generate_auth_hash(auth: AuthCredentials):
        return TPLinkKlap._md5(
            TPLinkKlap._md5(auth.username.encode())
            + TPLinkKlap._md5(auth.password.encode())
        )

    @staticmethod
    def generate_owner_hash(auth: AuthCredentials):
        """Return the MD5 hash of the username in this object."""
        return TPLinkKlap._md5(auth.username.encode())

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
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
            except SmartDeviceAuthenticationException as auex:
                _LOGGER.error("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    )
                continue

    async def _execute_query(self, request: str, retry_count: int) -> Dict:
        timeout = aiohttp.ClientTimeout(total=self.timeout)

        async with aiohttp.ClientSession(
            cookie_jar=self.jar, timeout=timeout
        ) as session:
            if not self.handshake_done:
                try:
                    await self.perform_handshake(session)

                except SmartDeviceAuthenticationException as auex:
                    _LOGGER.debug(
                        f"Unable to complete handshake for device {self.host}, authentication failed"
                    )
                    raise auex

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
                    raise SmartDeviceAuthenticationException(
                        "Got a security error after handshake completed"
                    )
                else:
                    raise SmartDeviceException(
                        "Device %s responded with %d to request with seq %d"
                        % (self.host, response_status)
                    )
            else:
                _LOGGER.debug(
                    f"Query posted at {datetime.datetime.now()}.  Host is {self.host}, Session cookie is {cookie}, Retry count is {retry_count}, Sequence is {seq}, Response status is {response_status}, Request was {request}"
                )

                self.handle_cookies(session, url)

                self.authentication_failed = False

                decrypted_response = self.encryption_session.decrypt(response_data)
                json_payload = json_loads(decrypted_response)

                _LOGGER.debug("%s << %s", self.host, pf(json_payload))

                return json_payload

    async def close(self) -> None:
        """Close the connection."""
        pass

    @staticmethod
    def _get_klap_owner(info: dict) -> Optional[str]:
        """Find owner given new-style discovery payload."""
        if "result" not in info:
            raise SmartDeviceAuthenticationException(
                "No 'result' in discovery response"
            )

        if "owner" not in info["result"]:
            return None

        return info["result"]["owner"]

    def _check_owners_match(self, info: dict):
        device_owner = self._get_klap_owner(info)
        if device_owner is not None:
            device_owner_bin = bytes.fromhex(device_owner)
        auth_owner = self.generate_owner_hash(self.auth_credentials)

        if device_owner != auth_owner:
            _LOGGER.debug(
                "Device {host} has owner {device_owner} and owner_bin {device_owner_bin} whereas the auth_owner is {auth_owner}.  Authentication will probably fail.".format(
                    host=self.host,
                    device_owner=device_owner,
                    device_owner_bin=device_owner_bin,
                    auth_owner=auth_owner.hex(),
                )
            )


class KlapEncryptionSession:
    def __init__(self, local_seed, remote_seed, user_hash):
        self._key = self._key_derive(local_seed, remote_seed, user_hash)
        (self._iv, self._seq) = self._iv_derive(local_seed, remote_seed, user_hash)
        self._sig = self._sig_derive(local_seed, remote_seed, user_hash)

    def _key_derive(self, local_seed, remote_seed, user_hash):
        payload = "lsk".encode("utf-8") + local_seed + remote_seed + user_hash
        return hashlib.sha256(payload).digest()[:16]

    def _iv_derive(self, local_seed, remote_seed, user_hash):
        # iv is first 16 bytes of sha256, where the last 4 bytes forms the
        # sequence number used in requests and is incremented on each request
        payload = "iv".encode("utf-8") + local_seed + remote_seed + user_hash
        fulliv = hashlib.sha256(payload).digest()
        seq = int.from_bytes(fulliv[-4:], "big", signed=True)
        return (fulliv[:12], seq)

    def _sig_derive(self, local_seed, remote_seed, user_hash):
        # used to create a hash with which to prefix each request
        payload = "ldk".encode("utf-8") + local_seed + remote_seed + user_hash
        return hashlib.sha256(payload).digest()[:28]

    def iv(self):
        seq = self._seq.to_bytes(4, "big", signed=True)
        iv = self._iv + seq
        assert len(iv) == 16
        return iv

    def encrypt(self, msg):
        self._seq = self._seq + 1
        if type(msg) == str:
            msg = msg.encode("utf-8")
        assert type(msg) == bytes
        cipher = AES.new(self._key, AES.MODE_CBC, self.iv())
        ciphertext = cipher.encrypt(Padding.pad(msg, AES.block_size))
        signature = hashlib.sha256(
            self._sig + self._seq.to_bytes(4, "big", signed=True) + ciphertext
        ).digest()
        return (signature + ciphertext, self._seq)

    def decrypt(self, msg):
        assert type(msg) == bytes
        cipher = AES.new(self._key, AES.MODE_CBC, self.iv())
        plaintext = Padding.unpad(cipher.decrypt(msg[32:]), AES.block_size).decode()
        return plaintext
