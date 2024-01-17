"""Module for HttpClientSession class."""
import logging
from typing import Dict, Optional, Type

import httpx

from .deviceconfig import DeviceConfig
from .exceptions import ConnectionException, SmartDeviceException, TimeoutException

logging.getLogger("httpx").propagate = False

InnerHttpType = Type[httpx.AsyncClient]


class HttpClientSession:
    """HttpClientSession Class."""

    def __init__(self, config: DeviceConfig) -> None:
        self._config = config
        self._default_client: httpx.AsyncClient = None

    @property
    def client(self):
        """Return the underlying http client."""
        if self._config.http_client and issubclass(
            self._config.http_client.__class__, httpx.AsyncClient
        ):
            return self._config.http_client

        if not self._default_client:
            self._default_client = httpx.AsyncClient()
        return self._default_client

    async def post(
        self,
        url,
        params=None,
        data=None,
        json=None,
        headers=None,
        cookies_dict: Optional[Dict[str, str]] = None,
    ):
        """Send an http post request to the device."""
        response_data = None
        cookies = None
        if cookies_dict:
            cookies = httpx.Cookies()
            for name, value in cookies_dict.items():
                cookies.set(name, value)
        self.client.cookies.clear()
        try:
            resp = await self.client.post(
                url,
                params=params,
                data=data,
                json=json,
                timeout=self._config.timeout,
                cookies=cookies,
                headers=headers,
            )
        except httpx.ConnectError as ex:
            raise ConnectionException(
                f"Unable to connect to the device: {self._config.host}: {ex}"
            ) from ex
        except httpx.TimeoutException as ex:
            raise TimeoutException(
                "Unable to query the device, " + f"timed out: {self._config.host}: {ex}"
            ) from ex
        except Exception as ex:
            raise SmartDeviceException(
                f"Unable to query the device: {self._config.host}: {ex}"
            ) from ex

        if resp.status_code == 200:
            response_data = resp.json() if json else resp.content

        return resp.status_code, response_data

    def get_cookie(self, cookie_name):
        """Return the cookie with cookie_name."""
        return self._default_client.cookies.get(cookie_name)

    async def close(self) -> None:
        """Close the protocol."""
        client = self._default_client
        self._default_client = None
        if client:
            await client.aclose()
