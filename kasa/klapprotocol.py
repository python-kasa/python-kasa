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

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util import Padding
from yarl import URL

from .auth import Auth
from .exceptions import SmartDeviceException
from .protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


class TPLinkKLAP(TPLinkSmartHomeProtocol):
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, used by newer firmware versions.
    """

    def __init__(self, host: str, authentication: Auth = Auth()) -> None:
        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.client_challenge = secrets.token_bytes(16)
        self.authenticator = authentication.authenticator()
        self.handshake_lock = asyncio.Lock()
        self.handshake_done = False

        super().__init__(host=host)

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    @staticmethod
    def _sha256(payload: bytes) -> bytes:
        return hashlib.sha256(payload).digest()

    async def _handshake(self, session) -> None:
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        # Handshake 1 has a payload of client_challenge
        # and a response of 16 bytes, followed by sha256(clientBytes | authenticator)

        url = f"http://{self.host}/app/handshake1"
        resp = await session.post(url, data=self.client_challenge)
        _LOGGER.debug("Got response of %d to handshake1", resp.status)
        if resp.status != 200:
            raise SmartDeviceException(
                "Device responded with %d to handshake1" % resp.status
            )

        response = await resp.read()
        self.server_challenge = response[0:16]
        server_hash = response[16:]

        _LOGGER.debug("Server bytes are: %s", self.server_challenge.hex())
        _LOGGER.debug("Server hash is: %s", server_hash.hex())

        # Check the response from the device
        local_hash = self._sha256(self.client_challenge + self.authenticator)

        if local_hash != server_hash:
            _LOGGER.debug(
                "Expected %s got %s in handshake1",
                local_hash.hex(),
                server_hash.hex(),
            )
            raise SmartDeviceException("Server response doesn't match our challenge")
        else:
            _LOGGER.debug("handshake1 hashes match")

        # We need to include only the TP_SESSIONID cookie - aiohttp's cookie handling
        # adds a bogus TIMEOUT cookie
        cookie = session.cookie_jar.filter_cookies(url).get("TP_SESSIONID")
        session.cookie_jar.clear()
        session.cookie_jar.update_cookies({"TP_SESSIONID": cookie}, URL(url))
        _LOGGER.debug("Cookie is %s", cookie)

        # Handshake 2 has the following payload:
        #    sha256(serverBytes | authenticator)
        url = f"http://{self.host}/app/handshake2"
        payload = self._sha256(self.server_challenge + self.authenticator)
        resp = await session.post(url, data=payload)
        _LOGGER.debug("Got response of %d to handshake2", resp.status)
        if resp.status != 200:
            raise SmartDeviceException(
                "Device responded with %d to handshake2" % resp.status
            )

        # Done handshaking, now we need to compute the encryption keys
        agreed = self.client_challenge + self.server_challenge + self.authenticator
        self.encrypt_key = self._sha256(b"lsk" + agreed)[:16]
        self.hmac_key = self._sha256(b"ldk" + agreed)[:28]
        fulliv = self._sha256(b"iv" + agreed)
        self.iv = fulliv[:12]
        self.seq = int.from_bytes(fulliv[-4:], "big", signed=True)
        self.handshake_done = True

    def _encrypt(self, plaintext: bytes, iv: bytes, seq: int) -> bytes:
        cipher = AES.new(self.encrypt_key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(Padding.pad(plaintext, AES.block_size))
        signature = self._sha256(
            self.hmac_key + seq.to_bytes(4, "big", signed=True) + ciphertext
        )
        return signature + ciphertext

    def _decrypt(self, payload: bytes, iv: bytes, seq: int) -> bytes:
        cipher = AES.new(self.encrypt_key, AES.MODE_CBC, iv)
        # In theory we should verify the hmac here too
        return Padding.unpad(cipher.decrypt(payload[32:]), AES.block_size)

    async def _ask(self, request: str) -> str:

        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            session = aiohttp.ClientSession(cookie_jar=self.jar, timeout=timeout)

            async with self.handshake_lock:
                if not self.handshake_done:
                    await self._handshake(session)

            msg_seq = self.seq
            msg_iv = self.iv + msg_seq.to_bytes(4, "big", signed=True)
            payload = self._encrypt(request.encode("utf-8"), msg_iv, msg_seq)

            url = f"http://{self.host}/app/request"
            resp = await session.post(url, params={"seq": msg_seq}, data=payload)
            _LOGGER.debug("Got response of %d to request", resp.status)

            # If we failed with a security error, force a new handshake next time
            if resp.status == 403:
                self.handshake_done = False

            if resp.status != 200:
                raise SmartDeviceException(
                    "Device responded with %d to request with seq %d"
                    % (resp.status, msg_seq)
                )
            response = await resp.read()
            return self._decrypt(response, msg_iv, msg_seq).decode("utf-8")
        finally:
            await session.close()
