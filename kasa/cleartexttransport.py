"""Implementation of the TP-Link cleartext, token-based transport seen on robovacs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Dict, cast

from yarl import URL

from .credentials import Credentials
from .deviceconfig import DeviceConfig
from .exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    _RetryableError,
)
from .httpclient import HttpClient
from .json import dumps as json_dumps
from .json import loads as json_loads
from .protocol import DEFAULT_CREDENTIALS, BaseTransport, get_default_credentials

_LOGGER = logging.getLogger(__name__)


ONE_DAY_SECONDS = 86400
SESSION_EXPIRE_BUFFER_SECONDS = 60 * 20


def _md5(payload: bytes) -> str:
    algo = hashlib.md5()  # noqa: S324
    algo.update(payload)
    return algo.hexdigest()


class TransportState(Enum):
    """Enum for transport state.

    TODO: cleartext requires only login
    """

    HANDSHAKE_REQUIRED = auto()  # Handshake needed
    LOGIN_REQUIRED = auto()  # Login needed
    ESTABLISHED = auto()  # Ready to send requests


class CleartextTokenTransport(BaseTransport):
    """Implementation of the AES encryption protocol.

    AES is the name used in device discovery for TP-Link's TAPO encryption
    protocol, sometimes used by newer firmware versions on kasa devices.
    """

    DEFAULT_PORT: int = 4433
    SESSION_COOKIE_NAME = "TP_SESSIONID"  # TODO: cleanup cookie handling
    TIMEOUT_COOKIE_NAME = "TIMEOUT"
    COMMON_HEADERS = {
        "Content-Type": "application/json",
        # "Accept": "application/json",
    }
    CONTENT_LENGTH = "Content-Length"
    BACKOFF_SECONDS_AFTER_LOGIN_ERROR = 1

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        super().__init__(config=config)

        if (
            not self._credentials or self._credentials.username is None
        ) and not self._credentials_hash:
            self._credentials = Credentials()
        if self._credentials:
            self._login_params = self._get_login_params(self._credentials)
        else:
            # TODO: Figure out how to handle credential hash
            self._login_params = json_loads(
                base64.b64decode(self._credentials_hash.encode()).decode()  # type: ignore[union-attr]
            )
        self._default_credentials: Credentials | None = None
        self._http_client: HttpClient = HttpClient(config)

        self._state = TransportState.LOGIN_REQUIRED
        self._session_expire_at: float | None = None

        # self._session_cookie: dict[str, str] | None = None

        self._app_url = URL(f"https://{self._host}:{self._port}/app")
        self._token_url: URL | None = None

        _LOGGER.debug("Created Cleartext transport for %s", self._host)

    @property
    def default_port(self) -> int:
        """Default port for the transport."""
        return self.DEFAULT_PORT

    @property
    def credentials_hash(self) -> str:
        """The hashed credentials used by the transport."""
        return base64.b64encode(json_dumps(self._login_params).encode()).decode()

    def _get_login_params(self, credentials: Credentials) -> dict[str, str]:
        """Get the login parameters based on the login_version."""
        un, pw = self.hash_credentials(credentials)
        # The password hash needs to be upper-case
        return {"password": pw.upper(), "username": un}

    @staticmethod
    def hash_credentials(credentials: Credentials) -> tuple[str, str]:
        """Hash the credentials."""
        un = credentials.username
        pw = _md5(credentials.password.encode())
        return un, pw

    def _handle_response_error_code(self, resp_dict: Any, msg: str) -> None:
        """Handle response errors to request reauth etc.

        TODO: This should probably be moved to the base class as
         it's common for all smart protocols?
        """
        error_code = SmartErrorCode(resp_dict.get("error_code"))  # type: ignore[arg-type]
        if error_code == SmartErrorCode.SUCCESS:
            return
        msg = f"{msg}: {self._host}: {error_code.name}({error_code.value})"
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            self._state = TransportState.HANDSHAKE_REQUIRED
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    async def send_cleartext_request(self, request: str) -> dict[str, Any]:
        """Send encrypted message as passthrough."""
        if self._state is TransportState.ESTABLISHED and self._token_url:
            _LOGGER.info("We are logged in, sending to %s", self._token_url)
            url = self._token_url
        else:
            _LOGGER.info("We are not logged in, sending to %s", self._app_url)
            url = self._app_url

        status_code, resp = await self._http_client.post(
            url,
            data=request.encode(),
            headers=self.COMMON_HEADERS,
            # cookies_dict=self._session_cookie,
        )
        _LOGGER.debug(f"Response is {status_code}: {resp!r}")
        resp_dict = json_loads(resp)

        if status_code != 200:
            raise KasaException(
                f"{self._host} responded with an unexpected "
                + f"status code {status_code} to passthrough"
            )

        self._handle_response_error_code(
            resp_dict, "Error sending secure_passthrough message"
        )

        if TYPE_CHECKING:
            resp_dict = cast(Dict[str, Any], resp_dict)

        result: str = resp_dict["result"]

        return result  # type: ignore[return-value]

    async def perform_login(self):
        """Login to the device."""
        _LOGGER.info("Trying to login")
        try:
            await self.try_login(self._login_params)
        except AuthenticationError as aex:
            try:
                if aex.error_code is not SmartErrorCode.LOGIN_ERROR:
                    raise aex
                if self._default_credentials is None:
                    self._default_credentials = get_default_credentials(
                        DEFAULT_CREDENTIALS["TAPO"]
                    )
                    await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_LOGIN_ERROR)
                await self.try_login(self._get_login_params(self._default_credentials))
                _LOGGER.debug(
                    "%s: logged in with default credentials",
                    self._host,
                )
            except AuthenticationError:
                raise
            except Exception as ex:
                raise KasaException(
                    "Unable to login and trying default "
                    + f"login raised another exception: {ex}",
                    ex,
                ) from ex

    async def try_login(self, login_params: dict[str, Any]) -> None:
        """Try to login with supplied login_params."""
        login_request = {
            "method": "login",
            "params": login_params,
            # "request_time_milis": round(time.time() * 1000),
        }
        request = json_dumps(login_request)

        resp_dict = await self.send_cleartext_request(request)
        self._handle_response_error_code(resp_dict, "Error logging in")
        login_token = resp_dict["result"]["token"]
        self._token_url = self._app_url.with_query(f"token={login_token}")
        _LOGGER.info("Our token url: %s", self._token_url)
        self._state = TransportState.ESTABLISHED

    def _session_expired(self):
        """Return true if session has expired."""
        return (
            self._session_expire_at is None
            or self._session_expire_at - time.time() <= 0
        )

    async def send(self, request: str) -> dict[str, Any]:
        """Send the request."""
        _LOGGER.info("Going to send %s", request)
        if self._state is not TransportState.ESTABLISHED or self._session_expired():
            _LOGGER.info(
                "Transport not established or session expired, performing login"
            )
            await self.perform_login()

        return await self.send_cleartext_request(request)

    async def close(self) -> None:
        """Close the http client and reset internal state."""
        await self.reset()
        await self._http_client.close()

    async def reset(self) -> None:
        """Reset internal handshake and login state."""
        self._state = TransportState.HANDSHAKE_REQUIRED
