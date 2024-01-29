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
from typing import Any, Dict, Union

from .exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    SMART_TIMEOUT_ERRORS,
    AuthenticationException,
    ConnectionException,
    RetryableException,
    SmartDeviceException,
    SmartErrorCode,
    TimeoutException,
)
from .json import dumps as json_dumps
from .protocol import BaseProtocol, BaseTransport, md5

_LOGGER = logging.getLogger(__name__)


class SmartProtocol(BaseProtocol):
    """Class for the new TPLink SMART protocol."""

    BACKOFF_SECONDS_AFTER_TIMEOUT = 1
    DEFAULT_MULTI_REQUEST_BATCH_SIZE = 5

    def __init__(
        self,
        *,
        transport: BaseTransport,
    ) -> None:
        """Create a protocol object."""
        super().__init__(transport=transport)
        self._terminal_uuid: str = base64.b64encode(md5(uuid.uuid4().bytes)).decode()
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
            return await self._query(request, retry_count)

    async def _query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(request, retry)
            except ConnectionException as sdex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise sdex
                continue
            except AuthenticationException as auex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to authenticate with %s, not retrying", self._host
                )
                raise auex
            except RetryableException as ex:
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                continue
            except TimeoutException as ex:
                await self._transport.reset()
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_TIMEOUT)
                continue
            except SmartDeviceException as ex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to query the device: %s, not retrying: %s",
                    self._host,
                    ex,
                )
                raise ex

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    async def _execute_multiple_query(self, request: Dict, retry_count: int) -> Dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        multi_result: Dict[str, Any] = {}
        smart_method = "multipleRequest"
        requests = [
            {"method": method, "params": params} for method, params in request.items()
        ]

        end = len(requests)
        # Break the requests down as there can be a size limit
        step = (
            self._transport._config.batch_size or self.DEFAULT_MULTI_REQUEST_BATCH_SIZE
        )
        for i in range(0, end, step):
            requests_step = requests[i : i + step]

            smart_params = {"requests": requests_step}
            smart_request = self.get_smart_request(smart_method, smart_params)
            if debug_enabled:
                _LOGGER.debug(
                    "%s multi-request-batch-%s >> %s",
                    self._host,
                    i + 1,
                    pf(smart_request),
                )
            response_step = await self._transport.send(smart_request)
            if debug_enabled:
                _LOGGER.debug(
                    "%s multi-request-batch-%s << %s",
                    self._host,
                    i + 1,
                    pf(response_step),
                )
            self._handle_response_error_code(response_step)
            responses = response_step["result"]["responses"]
            for response in responses:
                self._handle_response_error_code(response)
                result = response.get("result", None)
                multi_result[response["method"]] = result
        return multi_result

    async def _execute_query(self, request: Union[str, Dict], retry_count: int) -> Dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if isinstance(request, dict):
            if len(request) == 1:
                smart_method = next(iter(request))
                smart_params = request[smart_method]
            else:
                return await self._execute_multiple_query(request, retry_count)
        else:
            smart_method = request
            smart_params = None

        smart_request = self.get_smart_request(smart_method, smart_params)
        if debug_enabled:
            _LOGGER.debug(
                "%s >> %s",
                self._host,
                pf(smart_request),
            )
        response_data = await self._transport.send(smart_request)

        if debug_enabled:
            _LOGGER.debug(
                "%s << %s",
                self._host,
                pf(response_data),
            )

        self._handle_response_error_code(response_data)

        # Single set_ requests do not return a result
        result = response_data.get("result")
        return {smart_method: result}

    def _handle_response_error_code(self, resp_dict: dict):
        error_code = SmartErrorCode(resp_dict.get("error_code"))  # type: ignore[arg-type]
        if error_code == SmartErrorCode.SUCCESS:
            return
        msg = (
            f"Error querying device: {self._host}: "
            + f"{error_code.name}({error_code.value})"
        )
        if method := resp_dict.get("method"):
            msg += f" for method: {method}"
        if error_code in SMART_TIMEOUT_ERRORS:
            raise TimeoutException(msg, error_code=error_code)
        if error_code in SMART_RETRYABLE_ERRORS:
            raise RetryableException(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            raise AuthenticationException(msg, error_code=error_code)
        raise SmartDeviceException(msg, error_code=error_code)

    async def close(self) -> None:
        """Close the underlying transport."""
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


class _ChildProtocolWrapper(SmartProtocol):
    """Protocol wrapper for controlling child devices.

    This is an internal class used to communicate with child devices,
    and should not be used directly.

    This class overrides query() method of the protocol to modify all
    outgoing queries to use ``control_child`` command, and unwraps the
    device responses before returning to the caller.
    """

    def __init__(self, device_id: str, base_protocol: SmartProtocol):
        self._device_id = device_id
        self._protocol = base_protocol
        self._transport = base_protocol._transport

    def _get_method_and_params_for_request(self, request):
        """Return payload for wrapping.

        TODO: this does not support batches and requires refactoring in the future.
        """
        if isinstance(request, dict):
            if len(request) == 1:
                smart_method = next(iter(request))
                smart_params = request[smart_method]
            else:
                smart_method = "multipleRequest"
                requests = [
                    {"method": method, "params": params}
                    for method, params in request.items()
                ]
                smart_params = {"requests": requests}
        else:
            smart_method = request
            smart_params = None

        return smart_method, smart_params

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Wrap request inside control_child envelope."""
        method, params = self._get_method_and_params_for_request(request)
        request_data = {
            "method": method,
            "params": params,
        }
        wrapped_payload = {
            "control_child": {
                "device_id": self._device_id,
                "requestData": request_data,
            }
        }

        response = await self._protocol.query(wrapped_payload, retry_count)
        result = response.get("control_child")
        # Unwrap responseData for control_child
        if result and (response_data := result.get("responseData")):
            self._handle_response_error_code(response_data)
            result = response_data.get("result")

        # TODO: handle multipleRequest unwrapping

        return {method: result}

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""
