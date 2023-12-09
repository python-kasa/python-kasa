"""Implementation of the TP-Link AES Protocol.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

import asyncio
import base64
import logging
import time
import uuid
from pprint import pformat as pf
from typing import Dict, Optional, Union

import httpx

from .aestransport import AesTransport
from .credentials import Credentials
from .exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    SMART_TIMEOUT_ERRORS,
    AuthenticationException,
    RetryableException,
    SmartDeviceException,
    SmartErrorCode,
    TimeoutException,
)
from .json import dumps as json_dumps
from .protocol import BaseTransport, TPLinkProtocol, md5

_LOGGER = logging.getLogger(__name__)
logging.getLogger("httpx").propagate = False


class SmartProtocol(TPLinkProtocol):
    """Class for the new TPLink SMART protocol."""

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
        self._transport: BaseTransport = transport or AesTransport(
            host, credentials=self._credentials, timeout=timeout
        )
        self._terminal_uuid: Optional[str] = None
        self._request_id_generator = SnowflakeId(1, 1)
        self._query_lock = asyncio.Lock()

    def get_smart_request(self, method, params=None) -> str:
        """Get a request message as a string."""
        request = {
            "method": method,
            "params": params,
            "requestID": self._request_id_generator.generate_id(),
            "request_time_milis": round(time.time() * 1000),
            "terminal_uuid": self._terminal_uuid,
        }
        return json_dumps(request)

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Query the device retrying for retry_count on failure."""
        async with self._query_lock:
            resp_dict = await self._query(request, retry_count)

            if (
                error_code := SmartErrorCode(resp_dict.get("error_code"))
            ) != SmartErrorCode.SUCCESS:
                msg = (
                    f"Error querying device: {self.host}: "
                    + f"{error_code.name}({error_code.value})"
                )
                if error_code in SMART_TIMEOUT_ERRORS:
                    raise TimeoutException(msg)
                if error_code in SMART_RETRYABLE_ERRORS:
                    raise RetryableException(msg)
                if error_code in SMART_AUTHENTICATION_ERRORS:
                    raise AuthenticationException(msg)
                raise SmartDeviceException(msg)

            if "result" in resp_dict:
                return resp_dict["result"]
            return {}

    async def _query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
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
                if retry >= retry_count:
                    await self.close()
                    raise SmartDeviceException(
                        "Unable to connect to the device, "
                        + f"timed out: {self.host}: {tex}"
                    ) from tex
                await asyncio.sleep(2)
                continue
            except AuthenticationException as auex:
                await self.close()
                _LOGGER.debug("Unable to authenticate with %s, not retrying", self.host)
                raise auex
            except RetryableException as ex:
                if retry >= retry_count:
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise ex
                continue
            except TimeoutException as ex:
                if retry >= retry_count:
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise ex
                await asyncio.sleep(2)
                continue
            except Exception as ex:
                if retry >= retry_count:
                    await self.close()
                    _LOGGER.debug("Giving up on %s after %s retries", self.host, retry)
                    raise SmartDeviceException(
                        f"Unable to query the device {self.host}:{self.port}: {ex}"
                    ) from ex
                _LOGGER.debug(
                    "Unable to query the device %s, retrying: %s", self.host, ex
                )
                continue

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_query(self, request: Union[str, Dict], retry_count: int) -> Dict:
        if isinstance(request, dict):
            smart_method = next(iter(request))
            smart_params = request[smart_method]
        else:
            smart_method = request
            smart_params = None

        if self._transport.needs_handshake:
            await self._transport.handshake()

        if self._transport.needs_login:
            self._terminal_uuid = base64.b64encode(md5(uuid.uuid4().bytes)).decode(
                "UTF-8"
            )
            login_request = self.get_smart_request("login_device")
            await self._transport.login(login_request)

        smart_request = self.get_smart_request(smart_method, smart_params)
        _LOGGER.debug(
            "%s >> %s",
            self.host,
            _LOGGER.isEnabledFor(logging.DEBUG) and pf(smart_request),
        )
        response_data = await self._transport.send(smart_request)

        _LOGGER.debug(
            "%s << %s",
            self.host,
            _LOGGER.isEnabledFor(logging.DEBUG) and pf(response_data),
        )

        return response_data

    async def close(self) -> None:
        """Close the protocol."""
        await self._transport.close()


class SnowflakeId:
    """Class for generating snowflake ids."""

    EPOCH = 1420041600000  # Custom epoch (in milliseconds)
    WORKER_ID_BITS = 5
    DATA_CENTER_ID_BITS = 5
    SEQUENCE_BITS = 12

    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1
    MAX_DATA_CENTER_ID = (1 << DATA_CENTER_ID_BITS) - 1

    SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1

    def __init__(self, worker_id, data_center_id):
        if worker_id > SnowflakeId.MAX_WORKER_ID or worker_id < 0:
            raise ValueError(
                "Worker ID can't be greater than "
                + str(SnowflakeId.MAX_WORKER_ID)
                + " or less than 0"
            )
        if data_center_id > SnowflakeId.MAX_DATA_CENTER_ID or data_center_id < 0:
            raise ValueError(
                "Data center ID can't be greater than "
                + str(SnowflakeId.MAX_DATA_CENTER_ID)
                + " or less than 0"
            )

        self.worker_id = worker_id
        self.data_center_id = data_center_id
        self.sequence = 0
        self.last_timestamp = -1

    def generate_id(self):
        """Generate a snowflake id."""
        timestamp = self._current_millis()

        if timestamp < self.last_timestamp:
            raise ValueError("Clock moved backwards. Refusing to generate ID.")

        if timestamp == self.last_timestamp:
            # Within the same millisecond, increment the sequence number
            self.sequence = (self.sequence + 1) & SnowflakeId.SEQUENCE_MASK
            if self.sequence == 0:
                # Sequence exceeds its bit range, wait until the next millisecond
                timestamp = self._wait_next_millis(self.last_timestamp)
        else:
            # New millisecond, reset the sequence number
            self.sequence = 0

        # Update the last timestamp
        self.last_timestamp = timestamp

        # Generate and return the final ID
        return (
            (
                (timestamp - SnowflakeId.EPOCH)
                << (
                    SnowflakeId.WORKER_ID_BITS
                    + SnowflakeId.SEQUENCE_BITS
                    + SnowflakeId.DATA_CENTER_ID_BITS
                )
            )
            | (
                self.data_center_id
                << (SnowflakeId.SEQUENCE_BITS + SnowflakeId.WORKER_ID_BITS)
            )
            | (self.worker_id << SnowflakeId.SEQUENCE_BITS)
            | self.sequence
        )

    def _current_millis(self):
        return round(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp):
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp
