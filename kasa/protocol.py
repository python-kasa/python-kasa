"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import contextlib
import json
import logging
import struct
from pprint import pformat as pf
from typing import Dict, Optional, Union

from .exceptions import SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class TPLinkProtocol:
    """Base class for all TP-Link Smart Home communication."""

    DEFAULT_TIMEOUT = 5
    BLOCK_SIZE = 4

    def __init__(self, host: str) -> None:
        self.host = host
        self.timeout = TPLinkProtocol.DEFAULT_TIMEOUT

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: how many retries to do in case of failure
        :return: response dict
        """
        self._detect_event_loop_change()

        if not self.query_lock:
            self.query_lock = asyncio.Lock()

        if isinstance(request, dict):
            request = json.dumps(request)
            assert isinstance(request, str)

        for retry in range(retry_count + 1):
            try:
                _LOGGER.debug("> (%i) %s", len(request), request)
                response = await self._ask(request)
                json_payload = json.loads(response)
                _LOGGER.debug("< (%i) %s", len(response), pf(json_payload))

        with contextlib.suppress(Exception):
            self.reader = self.writer = None
            task = asyncio.open_connection(
                self.host, TPLinkSmartHomeProtocol.DEFAULT_PORT
            )
            self.reader, self.writer = await asyncio.wait_for(task, timeout=timeout)
            return True

        return False

    async def _execute_query(self, request: str) -> Dict:
        """Execute a query on the device and wait for the response."""
        assert self.writer is not None
        assert self.reader is not None
        debug_log = _LOGGER.isEnabledFor(logging.DEBUG)

        if debug_log:
            _LOGGER.debug("%s >> %s", self.host, request)
        self.writer.write(TPLinkSmartHomeProtocol.encrypt(request))
        await self.writer.drain()

        packed_block_size = await self.reader.readexactly(self.BLOCK_SIZE)
        length = struct.unpack(">I", packed_block_size)[0]

        buffer = await self.reader.readexactly(length)
        response = TPLinkSmartHomeProtocol.decrypt(buffer)
        json_payload = json.loads(response)
        if debug_log:
            _LOGGER.debug("%s << %s", self.host, pf(json_payload))

        return json_payload

    async def close(self):
        """Close the connection."""
        writer = self.writer
        self.reader = self.writer = None
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _reset(self):
        """Clear any varibles that should not survive between loops."""
        self.reader = self.writer = self.loop = self.query_lock = None

    async def _query(self, request: str, retry_count: int, timeout: int) -> Dict:
        """Try to query a device."""
        for retry in range(retry_count + 1):
            if not await self._connect(timeout):
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}"
                    )
                continue

            try:
                assert self.reader is not None
                assert self.writer is not None
                return await asyncio.wait_for(
                    self._execute_query(request), timeout=timeout
                )
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to query the device {self.host}: {ex}"
                    ) from ex

                _LOGGER.debug(
                    "Unable to query the device %s, retrying: %s", self.host, ex
                )

        raise SmartDeviceException("Not reached")

    async def _ask(self, request: str) -> str:
        raise SmartDeviceException("ask should be overridden")


class TPLinkSmartHomeProtocol(TPLinkProtocol):
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999

    def __init__(self, host: str):
        super().__init__(host=host)

    async def _ask(self, request: str) -> str:
        writer = None
        try:
            task = asyncio.open_connection(self.host, self.DEFAULT_PORT)
            reader, writer = await asyncio.wait_for(task, timeout=self.timeout)
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

            return TPLinkSmartHomeProtocol.decrypt(buffer[4:])

        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

        # make mypy happy, this should never be reached..
        await self.close()
        raise SmartDeviceException("Query reached somehow to unreachable")

    def __del__(self):
        if self.writer and self.loop and self.loop.is_running():
            self.writer.close()
        self._reset()

    @staticmethod
    def _xor_payload(unencrypted):
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        for unencryptedbyte in unencrypted:
            key = key ^ unencryptedbyte
            yield key

    @staticmethod
    def encrypt(request: str) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """
        plainbytes = request.encode()
        return struct.pack(">I", len(plainbytes)) + bytes(
            TPLinkSmartHomeProtocol._xor_payload(plainbytes)
        )

    @staticmethod
    def _xor_encrypted_payload(ciphertext):
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        for cipherbyte in ciphertext:
            plainbyte = key ^ cipherbyte
            key = cipherbyte
            yield plainbyte

    @staticmethod
    def decrypt(ciphertext: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        return bytes(
            TPLinkSmartHomeProtocol._xor_encrypted_payload(ciphertext)
        ).decode()
