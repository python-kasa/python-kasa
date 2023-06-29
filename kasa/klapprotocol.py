"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

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
from typing import Any, Dict, List, Optional, Set
from .json import dumps as json_dumps
from .json import loads as json_loads
from pprint import pformat as pf

_LOGGER = logging.getLogger(__name__)


class TPLinkKLAP(TPLinkProtocol):
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, used by newer firmware versions.
    """

    DEFAULT_PORT = 80
    DISCOVERY_PORT = 20002
    DISCOVERY_TARGET = ("255,255,255,255", DISCOVERY_PORT)
    DISCOVERY_BROADCAST_PAYLOAD = binascii.unhexlify("020000010000000000000000463cb5d3")
    DISCOVERY_QUERY = { "system": {"get_sysinfo": None}, }

    def __init__(self, host: str, authentication: Auth = Auth()) -> None:
        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self._client_challenge = secrets.token_bytes(16)
        #self.client_challenge = Random.get_random_bytes(16)
        self.authentication = authentication
        self._authentication_failed = False
        self.handshake_lock = asyncio.Lock()
        self.handshake_done = False
        self.timeout = self.DEFAULT_TIMEOUT

        super().__init__(host=host, port=self.DEFAULT_PORT)

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    @staticmethod
    def get_discovery_targets():
        return [("255.255.255.255", TPLinkKLAP.DISCOVERY_PORT)]

    @staticmethod
    def get_discovery_payload():

        return TPLinkKLAP.DISCOVERY_BROADCAST_PAYLOAD
    
    @staticmethod
    def is_discovery_response_for_this_protocol(port, info):
        return port == TPLinkKLAP.DISCOVERY_PORT


    def try_get_discovery_info(port, data):
        """Returns discovery info if the ports match and we can read the data"""
        # Depending on any future protocol changes the port check could be relaxed
        if port == TPLinkKLAP.DISCOVERY_PORT:
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
            info = await self.query(TPLinkKLAP.DISCOVERY_QUERY)
            return info
        except SmartDeviceException:
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
    async def session_post(session, url, params = None, data = None):
        return await session.post(url, params=params, data=data)
    
    def get_client_challenge(self):
        return self._client_challenge

    @staticmethod
    def handle_cookies(session, url):
        # We need to include only the TP_SESSIONID cookie - aiohttp's cookie handling
        # adds a bogus TIMEOUT cookie
        cookie = session.cookie_jar.filter_cookies(url).get("TP_SESSIONID")
        session.cookie_jar.clear()
        session.cookie_jar.update_cookies({"TP_SESSIONID": cookie}, URL(url))
        _LOGGER.debug("Cookie is %s", cookie)

    async def _handshake1(self, session) -> None:

        # Handshake 1 has a payload of client_challenge
        # and a response of 16 bytes, followed by sha256(clientBytes | authenticator)
        self.handshake_done = False

        payload = self.get_client_challenge()

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
        self.server_challenge = response[0:16]
        server_hash = response[16:]
        
        _LOGGER.debug("Server bytes are: %s", self.server_challenge.hex())
        _LOGGER.debug("Server hash is: %s", server_hash.hex())

        self.handle_cookies(session, url)

       
        local_hash = self._sha256(self.get_client_challenge() + self.authentication.authenticator())
        
        # Check the response from the device
        
        if local_hash != server_hash:
            _LOGGER.debug("Expected %s got %s in handshake1.  Checking if blank auth is a match", local_hash.hex(),server_hash.hex())
            
            blank_auth = Auth()
            blank_auth_hash = self.sha256(self.get_client_challenge() + blank_auth.authenticator())
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
        

    async def _handshake2(self, session) -> None:
        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)

        url = f"http://{self.host}/app/handshake2"

        payload = self._sha256(self.server_challenge + self.authentication.authenticator())

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
            self.handshake_done = True

    @staticmethod
    def compute_encryption_keys(client_challenge: bytes, server_challenge: bytes, authenticator: bytes):
        agreed = client_challenge + server_challenge + authenticator
        encrypt_key = TPLinkKLAP._sha256(b"lsk" + agreed)[:16]
        hmac_key = TPLinkKLAP._sha256(b"ldk" + agreed)[:28]
        fulliv = TPLinkKLAP._sha256(b"iv" + agreed)
        iv = fulliv[:12]
        seq = int.from_bytes(fulliv[-4:], "big", signed=True)

        return encrypt_key, hmac_key, iv, seq

    async def _handshake(self, session) -> None:
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        await self._handshake1(session)

        await self._handshake2(session)

        # Done handshaking, now we need to compute the encryption keys
        self.encrypt_key, self.hmac_key, self.iv, self.seq = self.compute_encryption_keys(self.get_client_challenge(), self.server_challenge, self.authentication.authenticator())
        
        

    async def _execute_query(self, request: str) -> Dict:

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            session = aiohttp.ClientSession(cookie_jar=self.jar, timeout=timeout)

            async with self.handshake_lock:
                if not self.handshake_done:
                    await self._handshake(session)

            if self.handshake_done:
                msg_seq = self.seq
                msg_iv = self.iv + msg_seq.to_bytes(4, "big", signed=True)
                encryption_key = self.encrypt_key
                hmac_key = self.hmac_key
                payload = TPLinkKLAP._klap_encrypt(request.encode("utf-8"), encryption_key, msg_iv, msg_seq, hmac_key)

                url = f"http://{self.host}/app/request"
                #resp = await session.post(url, params={"seq": msg_seq}, data=payload)
                resp = await self.session_post(session, url, params={"seq": msg_seq}, data=payload)
                _LOGGER.debug("Got response of %d to request", resp.status)

                # If we failed with a security error, force a new handshake next time
                if resp.status == 403:
                    self.handshake_done = False

                if resp.status != 200:
                    _LOGGER.error("Device responded with %d to request with seq %d" % (resp.status, msg_seq))
                    
                response = await resp.read()
                decrypted_response = TPLinkKLAP._klap_decrypt(response, encryption_key, msg_iv).decode("utf-8")
                json_payload = json_loads(decrypted_response)

                _LOGGER.debug("%s << %s", self.host, pf(json_payload))

                return json_payload
    
            else:
                raise SmartDeviceAuthenticationException("Unable to complete handshake")
        except Exception as ex:
            traceback.format_exc()
            raise ex
        finally:
            await session.close()

    @staticmethod
    def _klap_encrypt(plaintext: bytes, encryption_key: bytes,  iv: bytes, seq: int, hmac_key: bytes) -> bytes:
        cipher = AES.new(encryption_key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(Padding.pad(plaintext, AES.block_size))
        signature = TPLinkKLAP._sha256(
            hmac_key + seq.to_bytes(4, "big", signed=True) + ciphertext
        )
        return signature + ciphertext

    @staticmethod
    def encrypt(request: str, client_challenge: bytes, server_challenge: bytes, authenticator: bytes) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """

        encrypt_key, hmac_key, iv, seq = TPLinkKLAP.compute_encryption_keys(client_challenge, server_challenge, authenticator)
        
        iv = iv + seq.to_bytes(4, "big", signed=True)
        payload = TPLinkKLAP._klap_encrypt(request.encode(), encrypt_key, iv, seq, hmac_key)
        return payload

    @staticmethod
    def _klap_decrypt(payload: bytes, encryption_key: bytes, iv: bytes) -> bytes:
        cipher = AES.new(encryption_key, AES.MODE_CBC, iv)
        # In theory we should verify the hmac here too
        return Padding.unpad(cipher.decrypt(payload[32:]), AES.block_size)

    @staticmethod
    def decrypt(ciphertext: bytes, client_challenge: bytes, server_challenge: bytes, authenticator: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        encrypt_key, hmac_key, iv, seq = TPLinkKLAP.compute_encryption_keys(client_challenge, server_challenge, authenticator)

        iv = iv + seq.to_bytes(4, "big", signed=True)
        return TPLinkKLAP._klap_decrypt(ciphertext, encrypt_key, iv).decode()

    def _create_request(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ):
        request: Dict[str, Any] = {target: {cmd: arg}}
        if child_ids is not None:
            request = {"context": {"child_ids": child_ids}, target: {cmd: arg}}

        return request
    
   
    
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
