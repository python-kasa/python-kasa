"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import binascii
import hashlib
import json
import logging
import secrets
import struct
from pprint import pformat as pf
from typing import Dict, Union

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util import Padding
from yarl import URL

from .auth import Auth
from .exceptions import SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class TPLinkSmartHomeProtocol:
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    DEFAULT_TIMEOUT = 5

    @staticmethod
    async def query(host: str, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: how many retries to do in case of failure
        :return: response dict
        """
        if isinstance(request, dict):
            request = json.dumps(request)

        timeout = TPLinkSmartHomeProtocol.DEFAULT_TIMEOUT
        writer = None
        for retry in range(retry_count + 1):
            try:
                task = asyncio.open_connection(
                    host, TPLinkSmartHomeProtocol.DEFAULT_PORT
                )
                reader, writer = await asyncio.wait_for(task, timeout=timeout)
                _LOGGER.debug("> (%i) %s", len(request), request)
                writer.write(TPLinkSmartHomeProtocol.encrypt(request))
                await writer.drain()

                buffer = bytes()
                # Some devices send responses with a length header of 0 and
                # terminate with a zero size chunk. Others send the length and
                # will hang if we attempt to read more data.
                length = -1
                while True:
                    chunk = await reader.read(4096)
                    if length == -1:
                        length = struct.unpack(">I", chunk[0:4])[0]
                    buffer += chunk
                    if (length > 0 and len(buffer) >= length + 4) or not chunk:
                        break

                response = TPLinkSmartHomeProtocol.decrypt(buffer[4:])
                json_payload = json.loads(response)
                _LOGGER.debug("< (%i) %s", len(response), pf(json_payload))

                return json_payload

            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up after %s retries", retry)
                    raise SmartDeviceException(
                        "Unable to query the device: %s" % ex
                    ) from ex

                _LOGGER.debug("Unable to query the device, retrying: %s", ex)

            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    @staticmethod
    def encrypt(request: str) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR

        plainbytes = request.encode()
        buffer = bytearray(struct.pack(">I", len(plainbytes)))

        for plainbyte in plainbytes:
            cipherbyte = key ^ plainbyte
            key = cipherbyte
            buffer.append(cipherbyte)

        return bytes(buffer)

    @staticmethod
    def decrypt(ciphertext: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        buffer = []

        for cipherbyte in ciphertext:
            plainbyte = key ^ cipherbyte
            key = cipherbyte
            buffer.append(plainbyte)

        plaintext = bytes(buffer)

        return plaintext.decode()


class TPLinkKLAP:
    """Implementation of the KLAP encryption protocol.

    KLAP is the name used in device discovery for TP-Link's new encryption
    protocol, which appeared with firmware 1.1.0.
    """

    def __init__(self, host: str, authentication: Auth = Auth()) -> None:
        self.host = host
        self.jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self.clientBytes = secrets.token_bytes(16)
        self.authenticator = authentication.authenticator()
        self.handshake_lock = asyncio.Lock()
        self.handshake_done = False

        _LOGGER.debug("[KLAP] Created KLAP object for %s", self.host)

    async def __handshake(self, session) -> None:
        _LOGGER.debug("[KLAP] Starting handshake with %s", self.host)

        # Handshake 1 has a payload of clientBytes
        # and a response of 16 bytes, followed by sha256(clientBytes | authenticator)

        url = "http://%s/app/handshake1" % self.host
        resp = await session.post(url, data=self.clientBytes)
        _LOGGER.debug("Got response of %d to handshake1", resp.status)
        if resp.status != 200:
            raise SmartDeviceException(
                "Device responded with %d to handshake1" % resp.status
            )
        response = await resp.read()
        self.serverBytes = response[0:16]
        serverHash = response[16:]

        _LOGGER.debug("Server bytes are: %s", binascii.hexlify(self.serverBytes))
        _LOGGER.debug("Server hash is: %s", binascii.hexlify(serverHash))

        # Check the response from the device
        localHash = hashlib.sha256(self.clientBytes + self.authenticator).digest()

        if localHash != serverHash:
            _LOGGER.debug(
                "Expected %s got %s in handshake1",
                binascii.hexlify(localHash),
                binascii.hexlify(serverHash),
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
        url = "http://%s/app/handshake2" % self.host
        payload = hashlib.sha256(self.serverBytes + self.authenticator).digest()
        resp = await session.post(url, data=payload)
        _LOGGER.debug("Got response of %d to handshake2", resp.status)
        if resp.status != 200:
            raise SmartDeviceException(
                "Device responded with %d to handshake2" % resp.status
            )

        # Done handshaking, now we need to compute the encryption keys
        agreedBytes = self.clientBytes + self.serverBytes + self.authenticator
        self.encryptKey = hashlib.sha256(bytearray(b"lsk") + agreedBytes).digest()[:16]
        self.hmacKey = hashlib.sha256(bytearray(b"ldk") + agreedBytes).digest()[:28]
        fulliv = hashlib.sha256(bytearray(b"iv") + agreedBytes).digest()
        self.iv = fulliv[:12]
        self.seq = int.from_bytes(fulliv[-4:], "big", signed=True)
        self.handshake_done = True

    def __encrypt(self, plaintext: bytes, iv: bytes, seq: int) -> bytes:
        cipher = AES.new(self.encryptKey, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(Padding.pad(plaintext, AES.block_size))
        signature = hashlib.sha256(
            self.hmacKey + seq.to_bytes(4, "big", signed=True) + ciphertext
        ).digest()
        return signature + ciphertext

    def __decrypt(self, payload: bytes, iv: bytes, seq: int) -> bytes:
        cipher = AES.new(self.encryptKey, AES.MODE_CBC, iv)
        # In theory we should verify the hmac here too
        return Padding.unpad(cipher.decrypt(payload[32:]), AES.block_size)

    async def query(
        self, host: str, request: Union[str, Dict], retry_count: int = 3
    ) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: ignored, for backwards compatibility only
        :return: response dict
        """
        if host != self.host:
            raise SmartDeviceException("Host %s doesn't match configured host %s")

        if isinstance(request, dict):
            request = json.dumps(request)

        _LOGGER.debug("Sending request %s", request)

        try:
            session = aiohttp.ClientSession(cookie_jar=self.jar)

            async with self.handshake_lock:
                if not self.handshake_done:
                    await self.__handshake(session)

            msg_seq = self.seq
            msg_iv = self.iv + msg_seq.to_bytes(4, "big", signed=True)
            payload = self.__encrypt(request.encode("utf-8"), msg_iv, msg_seq)

            url = "http://%s/app/request" % self.host
            resp = await session.post(url, params={"seq": msg_seq}, data=payload)
            _LOGGER.debug("Got response of %d to request", resp.status)
            if resp.status != 200:
                raise SmartDeviceException(
                    "Device responded with %d to request with seq %d"
                    % (resp.status, msg_seq)
                )
            response = await resp.read()
            plaintext = self.__decrypt(response, msg_iv, msg_seq)
        finally:
            await session.close()

        return json.loads(plaintext)
