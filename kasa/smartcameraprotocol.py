"""Protocol implementation for controlling TP-Link Kasa Cam devices."""

import errno
import logging
from base64 import b64decode, b64encode
from pprint import pformat as pf
from typing import Dict
from urllib.parse import quote

import httpx

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout

from .exceptions import SmartDeviceException
from .json import loads as json_loads
from .protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)
_NO_RETRY_ERRORS = {errno.EHOSTDOWN, errno.EHOSTUNREACH, errno.ECONNREFUSED}


class SmartCameraProtocol(TPLinkSmartHomeProtocol):
    """Implementation of the Kasa Cam protocol."""

    DEFAULT_PORT = 10443

    def __init__(self, *args, **kwargs) -> None:
        self.credentials = kwargs.pop("credentials")
        super().__init__(*args, **kwargs)
        self.session: httpx.Client = None

    async def _connect(self, timeout: int) -> None:
        if self.session:
            return

        self.session = httpx.Client(
            base_url=f"https://{self.host}:{self.port}",
            auth=(
                self.credentials.username,
                b64encode(self.credentials.password.encode()),
            ),
            verify=False,  # noqa: S501 - Device certs are self-signed
        )

    async def _execute_query(self, request: str) -> Dict:
        """Execute a query on the device and wait for the response."""
        _LOGGER.debug("%s >> %s", self.host, request)

        encrypted_cmd = SmartCameraProtocol.encrypt(request)[4:]
        b64_cmd = b64encode(encrypted_cmd).decode()
        url_safe_cmd = quote(b64_cmd, safe="!~*'()")

        r = self.session.post("/data/LINKIE.json", data=f"content={url_safe_cmd}")
        json_payload = json_loads(SmartCameraProtocol.decrypt(b64decode(r.read())))
        _LOGGER.debug("%s << %s", self.host, pf(json_payload))
        return json_payload

    async def _query(self, request: str, retry_count: int, timeout: int) -> Dict:
        for retry in range(retry_count + 1):
            try:
                await self._connect(timeout)
            except ConnectionRefusedError as ex:
                await self.close()
                raise SmartDeviceException(
                    f"Unable to connect to the device: {self.host}:{self.port}"
                ) from ex
            except OSError as ex:
                await self.close()
                if ex.errno in _NO_RETRY_ERRORS or retry >= retry_count:
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}:{self.port}"
                    ) from ex
                continue
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to connect to the device: {self.host}:{self.port}"
                    ) from ex
                continue

            try:
                async with asyncio_timeout(timeout):
                    return await self._execute_query(request)
            except Exception as ex:
                await self.close()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to query the device {self.host}:{self.port}: {ex}"
                    ) from ex

                _LOGGER.debug(
                    "Unable to query the device %s, retrying: %s", self.host, ex
                )
        # Make Mypy happy
        raise SmartDeviceException("Query reached the unreachable.")

    def _reset(self) -> None:
        """Clear any varibles that should not survive between loops."""
        self.session = None

    def __del__(self) -> None:
        if self.session and self.loop and self.loop.is_running():
            # Since __del__ will be called when python does
            # garbage collection is can happen in the event loop thread
            # or in another thread so we need to make sure the call to
            # close is called safely with call_soon_threadsafe
            self.loop.call_soon_threadsafe(self.session.close)
        self._reset()
