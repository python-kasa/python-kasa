"""Module for HttpClientSession class."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from typing import Any

import aiohttp
from yarl import URL

from .deviceconfig import DeviceConfig
from .exceptions import (
    KasaException,
    TimeoutError,
    _ConnectionError,
)
from .json import loads as json_loads

_LOGGER = logging.getLogger(__name__)


def get_cookie_jar() -> aiohttp.CookieJar:
    """Return a new cookie jar with the correct options for device communication."""
    return aiohttp.CookieJar(unsafe=True, quote_cookie=False)


class HttpClient:
    """HttpClient Class."""

    # Some devices (only P100 so far) close the http connection after each request
    # and aiohttp doesn't seem to handle it. If a Client OS error is received the
    # http client will start ensuring that sequential requests have a wait delay.
    WAIT_BETWEEN_REQUESTS_ON_OSERROR = 0.25

    def __init__(self, config: DeviceConfig) -> None:
        self._config = config
        self._client_session: aiohttp.ClientSession | None = None
        self._jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self._last_url = URL(f"http://{self._config.host}/")

        self._wait_between_requests = 0.0
        self._last_request_time = 0.0

    @property
    def client(self) -> aiohttp.ClientSession:
        """Return the underlying http client."""
        if self._config.http_client and issubclass(
            self._config.http_client.__class__, aiohttp.ClientSession
        ):
            return self._config.http_client

        if not self._client_session:
            self._client_session = aiohttp.ClientSession(cookie_jar=get_cookie_jar())
        return self._client_session

    async def post(
        self,
        url: URL,
        *,
        params: dict[str, Any] | None = None,
        data: bytes | None = None,
        json: dict | Any | None = None,
        headers: dict[str, str] | None = None,
        cookies_dict: dict[str, str] | None = None,
        ssl: ssl.SSLContext | bool = False,
    ) -> tuple[int, dict | bytes | None]:
        """Send an http post request to the device.

        If the request is provided via the json parameter json will be returned.
        """
        # Once we know a device needs a wait between sequential queries always wait
        # first rather than keep erroring then waiting.
        if self._wait_between_requests:
            now = time.monotonic()
            gap = now - self._last_request_time
            if gap < self._wait_between_requests:
                sleep = self._wait_between_requests - gap
                _LOGGER.debug(
                    "Device %s waiting %s seconds to send request",
                    self._config.host,
                    sleep,
                )
                await asyncio.sleep(sleep)

        _LOGGER.debug("Posting to %s", url)
        response_data = None
        self._last_url = url
        self.client.cookie_jar.clear()
        return_json = bool(json)
        if self._config.timeout is None:
            _LOGGER.warning("Request timeout is set to None.")
        client_timeout = aiohttp.ClientTimeout(total=self._config.timeout)

        # If json is not a dict send as data.
        # This allows the json parameter to be used to pass other
        # types of data such as async_generator and still have json
        # returned.
        if json and not isinstance(json, dict):
            data = json
            json = None
        try:
            resp = await self.client.post(
                url,
                params=params,
                data=data,
                json=json,
                timeout=client_timeout,
                cookies=cookies_dict,
                headers=headers,
                ssl=ssl,
            )
            async with resp:
                response_data = await resp.read()

            if resp.status == 200:
                if return_json:
                    response_data = json_loads(response_data.decode())
            else:
                _LOGGER.debug(
                    "Device %s received status code %s with response %s",
                    self._config.host,
                    resp.status,
                    str(response_data),
                )
                if response_data and return_json:
                    try:
                        response_data = json_loads(response_data.decode())
                    except Exception:
                        _LOGGER.debug("Device %s response could not be parsed as json")

        except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as ex:
            if not self._wait_between_requests:
                _LOGGER.debug(
                    "Device %s received an os error, "
                    "enabling sequential request delay: %s",
                    self._config.host,
                    ex,
                )
                self._wait_between_requests = self.WAIT_BETWEEN_REQUESTS_ON_OSERROR
            self._last_request_time = time.monotonic()
            raise _ConnectionError(
                f"Device connection error: {self._config.host}: {ex}", ex
            ) from ex
        except (aiohttp.ServerTimeoutError, TimeoutError) as ex:
            raise TimeoutError(
                "Unable to query the device, "
                + f"timed out: {self._config.host}: {ex}",
                ex,
            ) from ex
        except Exception as ex:
            raise KasaException(
                f"Unable to query the device: {self._config.host}: {ex}", ex
            ) from ex

        # For performance only request system time if waiting is enabled
        if self._wait_between_requests:
            self._last_request_time = time.monotonic()

        return resp.status, response_data

    def get_cookie(self, cookie_name: str) -> str | None:
        """Return the cookie with cookie_name."""
        if cookie := self.client.cookie_jar.filter_cookies(self._last_url).get(
            cookie_name
        ):
            return cookie.value
        return None

    async def close(self) -> None:
        """Close the ClientSession."""
        client = self._client_session
        self._client_session = None
        if client:
            await client.close()
