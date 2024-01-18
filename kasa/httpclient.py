"""Module for HttpClientSession class."""
from typing import Any, Dict, Optional, Tuple, Union

import aiohttp

from .deviceconfig import DeviceConfig
from .exceptions import ConnectionException, SmartDeviceException, TimeoutException
from .json import loads as json_loads


def get_cookie_jar() -> aiohttp.CookieJar:
    """Return a new cookie jar with the correct options for device communication."""
    return aiohttp.CookieJar(unsafe=True, quote_cookie=False)


class HttpClient:
    """HttpClient Class."""

    def __init__(self, config: DeviceConfig) -> None:
        self._config = config
        self._client: aiohttp.ClientSession = None
        self._jar = aiohttp.CookieJar(unsafe=True, quote_cookie=False)
        self._last_url = f"http://{self._config.host}/"

    @property
    def client(self) -> aiohttp.ClientSession:
        """Return the underlying http client."""
        if self._config.http_client and issubclass(
            self._config.http_client.__class__, aiohttp.ClientSession
        ):
            return self._config.http_client

        if not self._client:
            self._client = aiohttp.ClientSession(cookie_jar=get_cookie_jar())
        return self._client

    async def post(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies_dict: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Optional[Union[Dict, bytes]]]:
        """Send an http post request to the device."""
        response_data = None
        self._last_url = url
        self.client.cookie_jar.clear()
        try:
            resp = await self.client.post(
                url,
                params=params,
                data=data,
                json=json,
                timeout=self._config.timeout,
                cookies=cookies_dict,
                headers=headers,
            )
        except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as ex:
            raise ConnectionException(
                f"Unable to connect to the device: {self._config.host}: {ex}"
            ) from ex
        except aiohttp.ServerTimeoutError as ex:
            raise TimeoutException(
                "Unable to query the device, " + f"timed out: {self._config.host}: {ex}"
            ) from ex
        except Exception as ex:
            raise SmartDeviceException(
                f"Unable to query the device: {self._config.host}: {ex}"
            ) from ex

        async with resp:
            if resp.status == 200:
                response_data = await resp.read()
                if json:
                    response_data = json_loads(response_data.decode())

        return resp.status, response_data

    def get_cookie(self, cookie_name: str) -> Optional[str]:
        """Return the cookie with cookie_name."""
        if cookie := self.client.cookie_jar.filter_cookies(self._last_url).get(
            cookie_name
        ):
            return cookie.value
        return None

    async def close(self) -> None:
        """Close the client."""
        client = self._client
        self._client = None
        if client:
            await client.close()
