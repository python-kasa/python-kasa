"""Module for the IOT legacy IOT KASA protocol."""
import asyncio
import logging
from typing import Dict, Union

from .exceptions import (
    AuthenticationException,
    ConnectionException,
    RetryableException,
    SmartDeviceException,
    TimeoutException,
)
from .json import dumps as json_dumps
from .protocol import BaseTransport, TPLinkProtocol

_LOGGER = logging.getLogger(__name__)


class IotProtocol(TPLinkProtocol):
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
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise sdex
                continue
            except AuthenticationException as auex:
                await self.close()
                _LOGGER.debug(
                    "Unable to authenticate with %s, not retrying", self._host
                )
                raise auex
            except RetryableException as ex:
                if retry >= retry_count:
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                continue
            except TimeoutException as ex:
                if retry >= retry_count:
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_TIMEOUT)
                continue
            except SmartDeviceException as ex:
                await self.close()
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
        """Close the protocol."""
        await self._transport.close()
