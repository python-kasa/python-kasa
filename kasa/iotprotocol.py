"""Module for the IOT legacy IOT KASA protocol."""
import asyncio
import logging
from typing import Dict, Optional, Union

from .deviceconfig import DeviceConfig
from .exceptions import (
    AuthenticationException,
    ConnectionException,
    RetryableException,
    SmartDeviceException,
    TimeoutException,
)
from .json import dumps as json_dumps
from .protocol import BaseProtocol, BaseTransport
from .xortransport import XorEncryption, XorTransport

_LOGGER = logging.getLogger(__name__)


class IotProtocol(BaseProtocol):
    """Class for the legacy TPLink IOT KASA Protocol."""

    BACKOFF_SECONDS_AFTER_TIMEOUT = 1

    def __init__(
        self,
        *,
        transport: BaseTransport,
    ) -> None:
        """Create a protocol object."""
        super().__init__(transport=transport)

        self._query_lock = asyncio.Lock()

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device retrying for retry_count on failure."""
        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)  # noqa: S101

        async with self._query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: str, retry_count: int = 3) -> Dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except ConnectionException as sdex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise sdex
                continue
            except AuthenticationException as auex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to authenticate with %s, not retrying", self._host
                )
                raise auex
            except RetryableException as ex:
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                continue
            except TimeoutException as ex:
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_TIMEOUT)
                continue
            except SmartDeviceException as ex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to query the device: %s, not retrying: %s",
                    self._host,
                    ex,
                )
                raise ex

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: str, retry_count: int) -> Dict:
        return await self._transport.send(request)

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()


class _deprecated_TPLinkSmartHomeProtocol(IotProtocol):
    def __init__(
        self,
        host: Optional[str] = None,
        *,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
        transport: Optional[BaseTransport] = None,
    ) -> None:
        """Create a protocol object."""
        if not host and not transport:
            raise SmartDeviceException("host or transport must be supplied")
        if not transport:
            config = DeviceConfig(
                host=host,  # type: ignore[arg-type]
                port_override=port,
                timeout=timeout or XorTransport.DEFAULT_TIMEOUT,
            )
            transport = XorTransport(config=config)
        super().__init__(transport=transport)

    @staticmethod
    def encrypt(request: str) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """
        return XorEncryption.encrypt(request)

    @staticmethod
    def decrypt(ciphertext: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        return XorEncryption.decrypt(ciphertext)
