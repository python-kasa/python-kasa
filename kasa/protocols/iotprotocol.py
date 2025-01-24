"""Module for the IOT legacy IOT KASA protocol."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pprint import pformat as pf
from typing import TYPE_CHECKING, Any

from ..deviceconfig import DeviceConfig
from ..exceptions import (
    AuthenticationError,
    KasaException,
    TimeoutError,
    _ConnectionError,
    _RetryableError,
)
from ..json import dumps as json_dumps
from ..transports import XorEncryption, XorTransport
from .protocol import BaseProtocol, mask_mac, redact_data

if TYPE_CHECKING:
    from ..transports import BaseTransport

_LOGGER = logging.getLogger(__name__)


def _mask_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def mask_child(child: dict[str, Any], index: int) -> dict[str, Any]:
        result = {
            **child,
            "id": f"SCRUBBED_CHILD_DEVICE_ID_{index + 1}",
        }
        # Will leave empty aliases as blank
        if child.get("alias"):
            result["alias"] = f"#MASKED_NAME# {index + 1}"
        return result

    return [mask_child(child, index) for index, child in enumerate(children)]


REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "latitude": lambda x: 0,
    "longitude": lambda x: 0,
    "latitude_i": lambda x: 0,
    "longitude_i": lambda x: 0,
    "deviceId": lambda x: "REDACTED_" + x[9::],
    "children": _mask_children,
    "alias": lambda x: "#MASKED_NAME#" if x else "",
    "mac": mask_mac,
    "mic_mac": mask_mac,
    "ssid": lambda x: "#MASKED_SSID#" if x else "",
    "oemId": lambda x: "REDACTED_" + x[9::],
    "username": lambda _: "user@example.com",  # cnCloud
    "hwId": lambda x: "REDACTED_" + x[9::],
}


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
        self._redact_data = True

    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Query the device retrying for retry_count on failure."""
        if isinstance(request, dict):
            request = json_dumps(request)
            assert isinstance(request, str)  # noqa: S101

        async with self._query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: str, retry_count: int = 3) -> dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except _ConnectionError as sdex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise sdex
                continue
            except AuthenticationError as auex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to authenticate with %s, not retrying", self._host
                )
                raise auex
            except _RetryableError as ex:
                if retry == 0:
                    _LOGGER.debug(
                        "Device %s got a retryable error, will retry %s times: %s",
                        self._host,
                        retry_count,
                        ex,
                    )
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                continue
            except TimeoutError as ex:
                if retry == 0:
                    _LOGGER.debug(
                        "Device %s got a timeout error, will retry %s times: %s",
                        self._host,
                        retry_count,
                        ex,
                    )
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_TIMEOUT)
                continue
            except KasaException as ex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to query the device: %s, not retrying: %s",
                    self._host,
                    ex,
                )
                raise ex

        # make mypy happy, this should never be reached..
        raise KasaException("Query reached somehow to unreachable")

    async def _execute_query(self, request: str, retry_count: int) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if debug_enabled:
            _LOGGER.debug(
                "%s >> %s",
                self._host,
                request,
            )
        resp = await self._transport.send(request)

        if debug_enabled:
            data = redact_data(resp, REDACTORS) if self._redact_data else resp
            _LOGGER.debug(
                "%s << %s",
                self._host,
                pf(data),
            )
        return resp

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()


class _deprecated_TPLinkSmartHomeProtocol(IotProtocol):
    def __init__(
        self,
        host: str | None = None,
        *,
        port: int | None = None,
        timeout: int | None = None,
        transport: BaseTransport | None = None,
    ) -> None:
        """Create a protocol object."""
        if not host and not transport:
            raise KasaException("host or transport must be supplied")
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
