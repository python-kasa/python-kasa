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


class TPLinkSmartHomeProtocol:
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    DEFAULT_TIMEOUT = 5

    BLOCK_SIZE = 4

    def __init__(self, host: str) -> None:
        """Create a protocol object."""
        self.host = host
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.query_lock: Optional[asyncio.Lock] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def _detect_event_loop_change(self) -> None:
        """Check if this object has been reused betwen event loops."""
        loop = asyncio.get_running_loop()
        if not self.loop:
            self.loop = loop
        elif self.loop != loop:
            _LOGGER.warning("Detected protocol reuse between different event loop")
            self._reset()

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
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

        timeout = TPLinkSmartHomeProtocol.DEFAULT_TIMEOUT

        async with self.query_lock:
            return await self._query(request, retry_count, timeout)

    async def _connect(self, timeout: int) -> bool:
        """Try to connect or reconnect to the device."""
        if self.writer:
            return True

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

        _LOGGER.debug("> (%i) %s", len(request), request)
        self.writer.write(TPLinkSmartHomeProtocol.encrypt(request))
        await self.writer.drain()

        packed_block_size = await self.reader.readexactly(self.BLOCK_SIZE)
        length = struct.unpack(">I", packed_block_size)[0]

        buffer = await self.reader.readexactly(length)
        response = TPLinkSmartHomeProtocol.decrypt(buffer)
        json_payload = json.loads(response)
        _LOGGER.debug("< (%i) %s", len(response), pf(json_payload))
        return json_payload

    async def close(self):
        """Close the connection."""
        writer = self.writer
        self._reset()
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _reset(self):
        """Clear any varibles that should not survive between loops."""
        self.writer = None
        self.reader = None
        self.query_lock = None
        self.loop = None

    async def _query(self, request: str, retry_count: int, timeout: int) -> Dict:
        """Try to query a device."""
        for retry in range(retry_count + 1):
            if not await self._connect(timeout):
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up after %s retries", retry)
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
                    _LOGGER.debug("Giving up after %s retries", retry)
                    raise SmartDeviceException(
                        f"Unable to query the device: {ex}"
                    ) from ex

                _LOGGER.debug("Unable to query the device, retrying: %s", ex)

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
