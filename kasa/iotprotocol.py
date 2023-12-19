"""Module for the IOT legacy IOT KASA protocol."""
import asyncio
import logging
from typing import Dict, Optional, Union

import httpx

from .credentials import Credentials
from .exceptions import AuthenticationException, SmartDeviceException
from .json import dumps as json_dumps
from .klaptransport import KlapTransport
from .protocol import BaseTransport, TPLinkProtocol

_LOGGER = logging.getLogger(__name__)


class IotProtocol(TPLinkProtocol):
    """Class for the legacy TPLink IOT KASA Protocol."""

    DEFAULT_PORT = 80

    def __init__(
        self,
        host: str,
        *,
        transport: Optional[BaseTransport] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host=host, port=self.DEFAULT_PORT)

        self._credentials: Credentials = credentials or Credentials(
            username="", password=""
        )
        self._transport: BaseTransport = transport or KlapTransport(
            host, credentials=self._credentials, timeout=timeout
        )

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
            except httpx.CloseError as sdex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {sdex}"
                    ) from sdex
                continue
            except httpx.ConnectError as cex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}: {cex}"
                ) from cex
            except TimeoutError as tex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device, timed out: {self.host}: {tex}"
                ) from tex
            except AuthenticationException as auex:
                _LOGGER.debug("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}: {ex}"
                    ) from ex
                continue

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: str, retry_count: int) -> Dict:
        return await self._transport.send(request)

    async def close(self) -> None:
        """Close the protocol."""
        await self._transport.close()
