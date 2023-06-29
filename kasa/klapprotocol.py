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
import traceback
import binascii

# pycryptodome
from Crypto import Random 
from Crypto.Cipher import AES
from Crypto.Util import Counter, Padding

import aiohttp

from yarl import URL
#from yarl import URL
from typing import Dict

from .auth import Auth
from .exceptions import SmartDeviceException, SmartDeviceAuthenticationException
from .protocol import TPLinkProtocol
from typing import Any, Dict, List, Optional, Set, Union
from .json import dumps as json_dumps
from .json import loads as json_loads
from pprint import pformat as pf

_LOGGER = logging.getLogger(__name__)


class TPLinkKlap(TPLinkProtocol):
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, used by newer firmware versions.
    """

    DEFAULT_PORT = 80
    DISCOVERY_PORT = 20002
    DISCOVERY_TARGET = ("255,255,255,255", DISCOVERY_PORT)
    DISCOVERY_BROADCAST_PAYLOAD = binascii.unhexlify("020000010000000000000000463cb5d3")
    DISCOVERY_QUERY = { "system": {"get_sysinfo": None}, }
    POST_QUERY_DELAY = 0.5
    POST_AUTH_FAILURE_DELAY = 2

    def __init__(self, host: str, authentication: Auth = Auth()) -> None:

        super().__init__(host=host, port=self.DEFAULT_PORT)

        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        
        self.authentication = authentication
        self._local_seed = secrets.token_bytes(16)
        self.local_auth_hash = self.generate_auth_hash(authentication)
        self.local_auth_owner = self.generate_owner_hash(authentication).hex()
        self._authentication_failed = False
        self.handshake_lock = asyncio.Lock()
        self.query_lock = asyncio.Lock()
        self.handshake_done = False
        self.timeout = self.timeout + (self.POST_QUERY_DELAY * 3)
        self.encryption_session = None

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    @staticmethod
    def get_discovery_targets():
        return [("255.255.255.255", TPLinkKlap.DISCOVERY_PORT)]

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
            except:
                return None
            
            isklap =    (
                        "result" in unauthenticated_info and 
                        "mgt_encrypt_schm" in unauthenticated_info["result"] and
                        "encrypt_type" in unauthenticated_info["result"]["mgt_encrypt_schm"] and 
                        unauthenticated_info["result"]["mgt_encrypt_schm"]["encrypt_type"] == "KLAP"
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
        except SmartDeviceException as sde:
            _LOGGER.debug("Unable to query discovery for %s with TPLinkKLAP", self.host)
            return None
        
    @staticmethod
    def requires_authentication():
        return True
    
    def authentication_failed(self):
        return self._authentication_failed
    
    @staticmethod
    def _sha256(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()
    
    @staticmethod
    def _md5(payload: bytes) -> bytes:
        return hashlib.md5(payload).digest()

    @staticmethod
    async def session_post(session, url, params = None, data = None):
        return await session.post(url, params=params, data=data)
    
    def get_local_seed(self):
        return self._local_seed

    @staticmethod
    async def do_wait(seconds):
        await asyncio.sleep(seconds)

    @staticmethod
    def handle_cookies(session, url):
        # We need to include only the TP_SESSIONID cookie - aiohttp's cookie handling
        # adds a bogus TIMEOUT cookie

        cookie = session.cookie_jar.filter_cookies(url).get("TP_SESSIONID")
        session.cookie_jar.clear()
        session.cookie_jar.update_cookies({"TP_SESSIONID": cookie}, URL(url))

        _LOGGER.debug("Cookie is %s", cookie)

    
    def clear_cookies(self, session):

        session.cookie_jar.clear()
        self.jar.clear()


    async def perform_handshake1(self, session) -> None:

        self.clear_cookies(session)

        # Handshake 1 has a payload of local_seed
        # and a response of 16 bytes, followed by sha256(clientBytes | authenticator)
        self.handshake_done = False

        payload = self.get_local_seed()

        url = f"http://{self.host}/app/handshake1"
        #resp = await session.post(url, data=payload)
        resp = await self.session_post(session, url, data=payload)

        _LOGGER.debug("Got response of %d to handshake1", resp.status)
        if resp.status != 200:
            self._authentication_failed = True
            raise SmartDeviceAuthenticationException(
                "Device responded with %d to handshake1" % resp.status
            )

        response = await resp.read()
        self.remote_seed = response[0:16]
        server_hash = response[16:]
        
        _LOGGER.debug("Server bytes are: %s", self.remote_seed.hex())
        _LOGGER.debug("Server hash is: %s", server_hash.hex())

        self.handle_cookies(session, url)

       
        local_hash = self._sha256(self.get_local_seed() + self.local_auth_hash)
        
        # Check the response from the device
        
        if local_hash != server_hash:
            _LOGGER.debug("Expected %s got %s in handshake1.  Checking if blank auth is a match", local_hash.hex(),server_hash.hex())
            
            blank_auth = Auth()
            blank_auth_hash = self._sha256(self.get_local_seed() + self.generate_auth_hash(blank_auth))
            if blank_auth_hash == server_hash:
                self.authentication = blank_auth
                _LOGGER.warn("Server response doesn't match our challenge on ip %s but an authentication with blank credentials matched", self.host)
            else:
                self._authentication_failed = True
                msg = "Server response doesn't match our challenge on ip {}".format(self.host)
                _LOGGER.error(msg)
                raise SmartDeviceAuthenticationException(msg)
        else:
            _LOGGER.debug("handshake1 hashes match")
            await self.do_wait(self.POST_QUERY_DELAY)
        

    async def perform_handshake2(self, session) -> None:
        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)

        url = f"http://{self.host}/app/handshake2"

        payload = self._sha256(self.remote_seed + self.local_auth_hash)

        #resp = await session.post(url, data=payload)
        resp = await self.session_post(session, url, data=payload)
        _LOGGER.debug("Got response of %d to handshake2", resp.status)
        if resp.status != 200:
            self._authentication_failed = True
            self.handshake_done = False
            raise SmartDeviceAuthenticationException(
                "Device responded with %d to handshake2" % resp.status
            )
        else:
            await self.do_wait(self.POST_QUERY_DELAY)

            self.handshake_done = True
            self.handle_cookies(session, url)

        


    async def perform_handshake(self, session, new_local_seed: bytes = None) -> Any:
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        if new_local_seed is not None:
            self._local_seed = new_local_seed

        await self.perform_handshake1(session)

        await self.perform_handshake2(session)

        self.encryption_session = KlapEncryptionSession(self.get_local_seed(), self.remote_seed, self.local_auth_hash)

    @staticmethod
    def generate_auth_hash(auth: Auth):
        return TPLinkKlap._md5(TPLinkKlap._md5(auth.username.encode()) + TPLinkKlap._md5(auth.password.encode()))
    
    @staticmethod
    def generate_owner_hash(auth: Auth):
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
                return await asyncio.wait_for(
                        self._execute_query(request), timeout=(self.timeout)
                    )
            except ConnectionRefusedError as ex:                
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}: {ex}"
                )
            except OSError as ex:
                #if ex.errno in _NO_RETRY_ERRORS or retry >= retry_count:
                if retry >= retry_count:
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    )
                continue
            except SmartDeviceAuthenticationException as auex:
                if retry >= retry_count:
                    _LOGGER.error("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceAuthenticationException("Unable to authenticate with device %s", self.host)
                else:
                    await self.do_wait(self.POST_AUTH_FAILURE_DELAY)
                continue
            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    )
                continue
    

    async def _execute_query(self, request: str) -> Dict:

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            session = aiohttp.ClientSession(cookie_jar=self.jar, timeout=timeout)

            try:
                async with self.handshake_lock:
                    if not self.handshake_done:
                        await self.perform_handshake(session)
                        
            except SmartDeviceAuthenticationException as auex:
                _LOGGER.error("Unable to complete handshake, authentication failed")
                raise auex

            if self.handshake_done:
            
                payload, seq = self.encryption_session.encrypt(request.encode())

                url = f"http://{self.host}/app/request"
                
                resp = await self.session_post(session, url, params={"seq": seq}, data=payload)
                _LOGGER.debug("Got response of %d to request", resp.status)

                self.handle_cookies(session, url)

                if resp.status != 200:
                    _LOGGER.error("Device %s responded with %d to request with seq %d" % (self.host, resp.status, seq))
                    # If we failed with a security error, force a new handshake next time and give the device some time
                    if resp.status == 403:
                        self.handshake_done = False
                        raise SmartDeviceAuthenticationException("Got a security error after handshake completed")
                    else:
                        raise SmartDeviceException("Device %s responded with %d to request with seq %d" % (self.host, resp.status))
                else:
                    response = await resp.read()
                    decrypted_response = self.encryption_session.decrypt(response)
                    json_payload = json_loads(decrypted_response)

                    _LOGGER.debug("%s << %s", self.host, pf(json_payload))

                    await self.do_wait(self.POST_QUERY_DELAY)

                    return json_payload
                    
            
        finally:
            await session.close()

    
    async def close(self) -> None:
        """Close the connection."""
        pass
    
    @staticmethod
    def _get_klap_owner(info: dict) -> Optional[str]:
        """Find owner given new-style discovery payload."""
        if "result" not in info:
            raise SmartDeviceAuthenticationException("No 'result' in discovery response")

        if "owner" not in info["result"]:
            return None

        return info["result"]["owner"]
    
    def _check_owners_match(self, info: dict):
        device_owner = self._get_klap_owner(info)
        if device_owner is not None:
                device_owner_bin = bytes.fromhex(device_owner)
        auth_owner = self.authentication.owner()
        
        if (device_owner != auth_owner):
            _LOGGER.debug("Device {host} has owner {device_owner} and owner_bin {device_owner_bin} whereas the auth_owner is {auth_owner}.  Authentication will probably fail.".format(host=self.host, device_owner=device_owner, device_owner_bin=device_owner_bin, auth_owner=auth_owner.hex()))

class KlapEncryptionSession:
  def __init__(self, local_seed, remote_seed, user_hash):
    self._key = self._key_derive(local_seed, remote_seed, user_hash)
    (self._iv, self._seq) = self._iv_derive(local_seed, remote_seed, user_hash)
    self._sig = self._sig_derive(local_seed, remote_seed, user_hash)

  def _key_derive(self, local_seed, remote_seed, user_hash):
    payload = 'lsk'.encode('utf-8') + local_seed + remote_seed + user_hash
    return hashlib.sha256(payload).digest()[:16]

  def _iv_derive(self, local_seed, remote_seed, user_hash):
    # iv is first 16 bytes of sha256, where the last 4 bytes forms the
    # sequence number used in requests and is incremented on each request
    payload = 'iv'.encode('utf-8') + local_seed + remote_seed + user_hash
    iv = hashlib.sha256(payload).digest()[:16]
    return (iv[:12], (int.from_bytes(iv[12:16], 'big') & 0x7fffffff))

  def _sig_derive(self, local_seed, remote_seed, user_hash):
    # used to create a hash with which to prefix each request
    payload = 'ldk'.encode('utf-8') + local_seed + remote_seed + user_hash
    return hashlib.sha256(payload).digest()[:28]

  def iv(self):
    seq = self._seq.to_bytes(4, 'big')
    iv = self._iv + seq
    assert(len(iv) == 16)
    return iv
  

  def encrypt(self, msg):
    self._seq = self._seq + 1
    if (type(msg) == str):
      msg = msg.encode('utf-8')
    assert(type(msg) == bytes)
    cipher = AES.new(self._key, AES.MODE_CBC, self.iv())
    ciphertext = cipher.encrypt(Padding.pad(msg, AES.block_size))
    signature = hashlib.sha256(self._sig + self._seq.to_bytes(4, 'big') + ciphertext).digest()
    return (signature + ciphertext, self._seq)

  def decrypt(self, msg):
    assert(type(msg) == bytes)
    cipher = AES.new(self._key, AES.MODE_CBC, self.iv())
    plaintext = Padding.unpad(cipher.decrypt(msg[32:]), AES.block_size).decode()
    return plaintext

