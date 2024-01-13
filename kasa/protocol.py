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
import errno
import logging
import socket
import struct
from abc import ABC, abstractmethod
from pprint import pformat as pf
from typing import Dict, Generator, Optional, Union

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout
from cryptography.hazmat.primitives import hashes

from .deviceconfig import DeviceConfig
from .exceptions import SmartDeviceException
from .json import dumps as json_dumps
from .json import loads as json_loads

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}
_UNSIGNED_INT_NETWORK_ORDER = struct.Struct(">I")


def md5(payload: bytes) -> bytes:
    """Return an md5 hash of the payload."""
    digest = hashes.Hash(hashes.MD5())  # noqa: S303
    digest.update(payload)
    hash = digest.finalize()
    return hash


class BaseTransport(ABC):
    """Base class for all TP-Link protocol transports."""

    DEFAULT_TIMEOUT = 5

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        """Create a protocol object."""
        self._config = config
        self._host = config.host
        self._port = config.port_override or self.default_port
        self._credentials = config.credentials
        self._credentials_hash = config.credentials_hash
        self._timeout = config.timeout

    @property
    @abstractmethod
    def default_port(self) -> int:
        """The default port for the transport."""

    @property
    @abstractmethod
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""

    @abstractmethod
    async def send(self, request: str) -> Dict:
        """Send a message to the device and return a response."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport.  Abstract method to be overriden."""


class TPLinkProtocol(ABC):
    """Base class for all TP-Link Smart Home communication."""

    def __init__(
        self,
        *,
        transport: BaseTransport,
    ) -> None:
        """Create a protocol object."""
        self._transport = transport

    @property
    def _host(self):
        return self._transport._host

    @property
    def config(self) -> DeviceConfig:
        """Return the connection parameters the device is using."""
        return self._transport._config

    @abstractmethod
    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device for the protocol.  Abstract method to be overriden."""

    @abstractmethod
    async def close(self) -> None:
        """Close the protocol.  Abstract method to be overriden."""


class _XorTransport(BaseTransport):
    """Implementation of the Xor encryption transport.

    WIP, currently only to ensure consistent __init__ method signatures
    for protocol classes.  Will eventually incorporate the logic from
    TPLinkSmartHomeProtocol to simplify the API and re-use the IotProtocol
    class.
    """

    DEFAULT_PORT: int = 9999

    def __init__(self, *, config: DeviceConfig) -> None:
        super().__init__(config=config)

    @property
    def default_port(self):
        """Default port for the transport."""
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""
        return ""

    async def send(self, request: str) -> Dict:
        """Send a message to the device and return a response."""
        return {}

    async def close(self) -> None:
        """Close the transport.  Abstract method to be overriden."""


class TPLinkSmartHomeProtocol(TPLinkProtocol):
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    BLOCK_SIZE = 4

    def __init__(
        self,
        *,
        transport: BaseTransport,
    ) -> None:
        """Create a protocol object."""
        super().__init__(transport=transport)

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.query_lock = asyncio.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        self._timeout = self._transport._timeout
        self._port = self._transport._port

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: how many retries to do in case of failure
        :return: response dict
        """
        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)  # noqa: S101

        async with self.query_lock:
            return await self._query(request, retry_count, self._timeout)  # type: ignore[arg-type]

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

    async def _execute_query(self, request: str) -> Dict:
        """Execute a query on the device and wait for the response."""
        assert self.writer is not None  # noqa: S101
        assert self.reader is not None  # noqa: S101
        debug_log = _LOGGER.isEnabledFor(logging.DEBUG)
        if debug_log:
            _LOGGER.debug("%s >> %s", self._host, request)
        self.writer.write(TPLinkSmartHomeProtocol.encrypt(request))
        await self.writer.drain()

        packed_block_size = await self.reader.readexactly(self.BLOCK_SIZE)
        length = _UNSIGNED_INT_NETWORK_ORDER.unpack(packed_block_size)[0]

        buffer = await self.reader.readexactly(length)
        response = TPLinkSmartHomeProtocol.decrypt(buffer)
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

    def _reset(self) -> None:
        """Clear any varibles that should not survive between loops."""
        self.reader = self.writer = None

    async def _query(self, request: str, retry_count: int, timeout: int) -> Dict:
        """Try to query a device."""
        #
        # Most of the time we will already be connected if the device is online
        # and the connect call will do nothing and return right away
        #
        # However, if we get an unrecoverable error (_NO_RETRY_ERRORS and
        # ConnectionRefusedError) we do not want to keep trying since many
        # connection open/close operations in the same time frame can block
        # the event loop.
        # This is especially import when there are multiple tplink devices being polled.
        for retry in range(retry_count + 1):
            try:
                await self._connect(timeout)
            except ConnectionRefusedError as ex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self._host}:{self._port}: {ex}"
                ) from ex
            except OSError as ex:
                await self.close()
                if ex.errno in _NO_RETRY_ERRORS or retry >= retry_count:
                    raise SmartDeviceException(
                        f"Unable to connect to the device:"
                        f" {self._host}:{self._port}: {ex}"
                    ) from ex
                continue
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device:"
                        f" {self._host}:{self._port}: {ex}"
                    ) from ex
                continue
            except BaseException as ex:
                # Likely something cancelled the task so we need to close the connection
                # as we are not in an indeterminate state
                self.close_without_wait()
                _LOGGER.debug(
                    "%s: BaseException during connect, closing connection: %s",
                    self._host,
                    ex,
                )
                raise

            try:
                assert self.reader is not None  # noqa: S101
                assert self.writer is not None  # noqa: S101
                async with asyncio_timeout(timeout):
                    return await self._execute_query(request)
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise SmartDeviceException(
                        f"Unable to query the device {self._host}:{self._port}: {ex}"
                    ) from ex

                _LOGGER.debug(
                    "Unable to query the device %s, retrying: %s", self._host, ex
                )
            except BaseException as ex:
                # Likely something cancelled the task so we need to close the connection
                # as we are not in an indeterminate state
                self.close_without_wait()
                _LOGGER.debug(
                    "%s: BaseException during query, closing connection: %s",
                    self._host,
                    ex,
                )
                raise

        # make mypy happy, this should never be reached..
        await self.close()
        raise SmartDeviceException("Query reached somehow to unreachable")

    def __del__(self) -> None:
        if self.writer and self.loop and self.loop.is_running():
            # Since __del__ will be called when python does
            # garbage collection is can happen in the event loop thread
            # or in another thread so we need to make sure the call to
            # close is called safely with call_soon_threadsafe
            self.loop.call_soon_threadsafe(self.writer.close)
        self._reset()

    @staticmethod
    def _xor_payload(unencrypted: bytes) -> Generator[int, None, None]:
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
        return _UNSIGNED_INT_NETWORK_ORDER.pack(len(plainbytes)) + bytes(
            TPLinkSmartHomeProtocol._xor_payload(plainbytes)
        )

    @staticmethod
    def _xor_encrypted_payload(ciphertext: bytes) -> Generator[int, None, None]:
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


# Try to load the kasa_crypt module and if it is available
try:
    from kasa_crypt import decrypt, encrypt

    TPLinkSmartHomeProtocol.decrypt = decrypt  # type: ignore[method-assign]
    TPLinkSmartHomeProtocol.encrypt = encrypt  # type: ignore[method-assign]
except ImportError:
    pass
