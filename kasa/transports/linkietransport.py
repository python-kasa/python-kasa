"""Implementation of the linkie kasa camera transport."""

from __future__ import annotations

import asyncio
import base64
import logging
import ssl
from typing import TYPE_CHECKING, cast
from urllib.parse import quote

from yarl import URL

from kasa.credentials import DEFAULT_CREDENTIALS, get_default_credentials
from kasa.deviceconfig import DeviceConfig
from kasa.exceptions import KasaException, _RetryableError
from kasa.httpclient import HttpClient
from kasa.json import loads as json_loads
from kasa.transports.xortransport import XorEncryption

from .basetransport import BaseTransport

_LOGGER = logging.getLogger(__name__)


class LinkieTransportV2(BaseTransport):
    """Implementation of the Linkie encryption protocol.

    Linkie is used as the endpoint for TP-Link's camera encryption
    protocol, used by newer firmware versions.
    """

    DEFAULT_PORT: int = 10443
    CIPHERS = ":".join(
        [
            "AES256-GCM-SHA384",
            "AES256-SHA256",
            "AES128-GCM-SHA256",
            "AES128-SHA256",
            "AES256-SHA",
        ]
    )

    def __init__(self, *, config: DeviceConfig) -> None:
        super().__init__(config=config)
        self._http_client = HttpClient(config)
        self._ssl_context: ssl.SSLContext | None = None
        self._app_url = URL(f"https://{self._host}:{self._port}/data/LINKIE2.json")

        self._headers = {
            "Authorization": f"Basic {self.credentials_hash}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        if port := self._config.connection_type.http_port:
            return port
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""
        creds = get_default_credentials(DEFAULT_CREDENTIALS["KASACAMERA"])
        creds_combined = f"{creds.username}:{creds.password}"
        return base64.b64encode(creds_combined.encode()).decode()

    async def _execute_send(self, request: str) -> dict:
        """Execute a query on the device and wait for the response."""
        _LOGGER.debug("%s >> %s", self._host, request)

        encrypted_cmd = XorEncryption.encrypt(request)[4:]
        b64_cmd = base64.b64encode(encrypted_cmd).decode()
        url_safe_cmd = quote(b64_cmd, safe="!~*'()")

        status_code, response = await self._http_client.post(
            self._app_url,
            headers=self._headers,
            data=f"content={url_safe_cmd}".encode(),
            ssl=await self._get_ssl_context(),
        )

        if TYPE_CHECKING:
            response = cast(bytes, response)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        # Expected response
        try:
            json_payload: dict = json_loads(
                XorEncryption.decrypt(base64.b64decode(response))
            )
            _LOGGER.debug("%s << %s", self._host, json_payload)
            return json_payload
        except Exception:  # noqa: S110
            pass

        # Device returned error as json plaintext
        to_raise: KasaException | None = None
        try:
            error_payload: dict = json_loads(response)
            to_raise = KasaException(f"Device {self._host} send error: {error_payload}")
        except Exception as ex:
            raise KasaException("Unable to read response") from ex
        raise to_raise

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset the transport.

        NOOP for this transport.
        """

    async def send(self, request: str) -> dict:
        """Send a message to the device and return a response."""
        try:
            return await self._execute_send(request)
        except Exception as ex:
            await self.reset()
            raise _RetryableError(
                f"Unable to query the device {self._host}:{self._port}: {ex}"
            ) from ex

    async def _get_ssl_context(self) -> ssl.SSLContext:
        if not self._ssl_context:
            loop = asyncio.get_running_loop()
            self._ssl_context = await loop.run_in_executor(
                None, self._create_ssl_context
            )
        return self._ssl_context

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.set_ciphers(self.CIPHERS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
