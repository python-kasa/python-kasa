"""Implementation of the legacy TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import socket
import struct
from pprint import pformat as pf
from typing import Generator

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout

from .deviceconfig import DeviceConfig
from .exceptions import KasaException, _RetryableError
from .json import loads as json_loads
from .protocol import BaseTransport

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}
_UNSIGNED_INT_NETWORK_ORDER = struct.Struct(">I")


class XorTransport(BaseTransport):
    """XorTransport class."""

    DEFAULT_PORT: int = 9999
    BLOCK_SIZE = 4

    def __init__(self, *, config: DeviceConfig) -> None:
        super().__init__(config=config)
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.query_lock = asyncio.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    @property
    def default_port(self):
        """Default port for the transport."""
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""
        return ""

    async def _connect(self, timeout: int) -> None:
        """Try to connect or reconnect to the device."""
        if self.writer:
            return
        self.reader = self.writer = None

        task = asyncio.open_connection(self._host, self._port)
        async with asyncio_timeout(timeout):
            self.reader, self.writer = await task
            sock: socket.socket = self.writer.get_extra_info("socket")
            # Ensure our packets get sent without delay as we do all
            # our writes in a single go and we do not want any buffering
            # which would needlessly delay the request or risk overloading
            # the buffer on the device
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    async def _execute_send(self, request: str) -> dict:
        """Execute a query on the device and wait for the response."""
        assert self.writer is not None  # noqa: S101
        assert self.reader is not None  # noqa: S101
        debug_log = _LOGGER.isEnabledFor(logging.DEBUG)
        if debug_log:
            _LOGGER.debug("%s >> %s", self._host, request)
        self.writer.write(XorEncryption.encrypt(request))
        await self.writer.drain()

        packed_block_size = await self.reader.readexactly(self.BLOCK_SIZE)
        length = _UNSIGNED_INT_NETWORK_ORDER.unpack(packed_block_size)[0]

        buffer = await self.reader.readexactly(length)
        response = XorEncryption.decrypt(buffer)
        json_payload = json_loads(response)
        if debug_log:
            _LOGGER.debug("%s << %s", self._host, pf(json_payload))

        return json_payload

    async def close(self) -> None:
        """Close the connection."""
        writer = self.writer
        self.close_without_wait()
        if writer:
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def close_without_wait(self) -> None:
        """Close the connection without waiting for the connection to close."""
        writer = self.writer
        self.reader = self.writer = None
        if writer:
            writer.close()

    async def reset(self) -> None:
        """Reset the transport.

        The transport cannot be reset so we must close instead.
        """
        await self.close()

    async def send(self, request: str) -> dict:
        """Send a message to the device and return a response."""
        #
        # Most of the time we will already be connected if the device is online
        # and the connect call will do nothing and return right away
        #
        # However, if we get an unrecoverable error (_NO_RETRY_ERRORS and
        # ConnectionRefusedError) we do not want to keep trying since many
        # connection open/close operations in the same time frame can block
        # the event loop.
        # This is especially import when there are multiple tplink devices being polled.
        try:
            await self._connect(self._timeout)
        except ConnectionRefusedError as ex:
            await self.reset()
            raise KasaException(
                f"Unable to connect to the device: {self._host}:{self._port}: {ex}"
            ) from ex
        except OSError as ex:
            await self.reset()
            if ex.errno in _NO_RETRY_ERRORS:
                raise KasaException(
                    f"Unable to connect to the device:"
                    f" {self._host}:{self._port}: {ex}"
                ) from ex
            else:
                raise _RetryableError(
                    f"Unable to connect to the device:"
                    f" {self._host}:{self._port}: {ex}"
                ) from ex
        except Exception as ex:
            await self.reset()
            raise _RetryableError(
                f"Unable to connect to the device:" f" {self._host}:{self._port}: {ex}"
            ) from ex
        except BaseException:
            # Likely something cancelled the task so we need to close the connection
            # as we are not in an indeterminate state
            self.close_without_wait()
            raise

        try:
            assert self.reader is not None  # noqa: S101
            assert self.writer is not None  # noqa: S101
            async with asyncio_timeout(self._timeout):
                return await self._execute_send(request)
        except Exception as ex:
            await self.reset()
            raise _RetryableError(
                f"Unable to query the device {self._host}:{self._port}: {ex}"
            ) from ex
        except BaseException:
            # Likely something cancelled the task so we need to close the connection
            # as we are not in an indeterminate state
            self.close_without_wait()
            raise

    def __del__(self) -> None:
        if self.writer and self.loop and self.loop.is_running():
            # Since __del__ will be called when python does
            # garbage collection is can happen in the event loop thread
            # or in another thread so we need to make sure the call to
            # close is called safely with call_soon_threadsafe
            self.loop.call_soon_threadsafe(self.writer.close)


class XorEncryption:
    """XorEncryption class."""

    INITIALIZATION_VECTOR = 171

    @staticmethod
    def _xor_payload(unencrypted: bytes) -> Generator[int, None, None]:
        key = XorEncryption.INITIALIZATION_VECTOR
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
        return _UNSIGNED_INT_NETWORK_ORDER.pack(len(plainbytes)) + bytes(
            XorEncryption._xor_payload(plainbytes)
        )

    @staticmethod
    def _xor_encrypted_payload(ciphertext: bytes) -> Generator[int, None, None]:
        key = XorEncryption.INITIALIZATION_VECTOR
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
        return bytes(XorEncryption._xor_encrypted_payload(ciphertext)).decode()


# Try to load the kasa_crypt module and if it is available
try:
    from kasa_crypt import decrypt, encrypt

    XorEncryption.decrypt = decrypt  # type: ignore[method-assign]
    XorEncryption.encrypt = encrypt  # type: ignore[method-assign]
except ImportError:
    pass
