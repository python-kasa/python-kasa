"""Implementation of the TP-Link AES Protocol.

Based on the work of https://github.com/petretiandrea/plugp100
under compatible GNU GPL3 license.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import uuid
from collections.abc import Callable
from pprint import pformat as pf
from typing import TYPE_CHECKING, Any

from ..exceptions import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    AuthenticationError,
    DeviceError,
    KasaException,
    SmartErrorCode,
    TimeoutError,
    _ConnectionError,
    _RetryableError,
)
from ..json import dumps as json_dumps
from .protocol import BaseProtocol, mask_mac, md5, redact_data

if TYPE_CHECKING:
    from ..transports import BaseTransport


_LOGGER = logging.getLogger(__name__)


def _mask_area_list(area_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def mask_area(area: dict[str, Any]) -> dict[str, Any]:
        result = {**area}
        # Will leave empty names as blank
        if area.get("name"):
            result["name"] = "I01BU0tFRF9OQU1FIw=="  # #MASKED_NAME#
        return result

    return [mask_area(area) for area in area_list]


REDACTORS: dict[str, Callable[[Any], Any] | None] = {
    "latitude": lambda x: 0,
    "longitude": lambda x: 0,
    "la": lambda x: 0,  # lat on ks240
    "lo": lambda x: 0,  # lon on ks240
    "device_id": lambda x: "REDACTED_" + x[9::],
    "parent_device_id": lambda x: "REDACTED_" + x[9::],  # Hub attached children
    "original_device_id": lambda x: "REDACTED_" + x[9::],  # Strip children
    "nickname": lambda x: "I01BU0tFRF9OQU1FIw==" if x else "",
    "mac": mask_mac,
    "ssid": lambda x: "I01BU0tFRF9TU0lEIw==" if x else "",
    "bssid": lambda _: "000000000000",
    "channel": lambda _: 0,
    "oem_id": lambda x: "REDACTED_" + x[9::],
    "hw_id": lambda x: "REDACTED_" + x[9::],
    "fw_id": lambda x: "REDACTED_" + x[9::],
    "setup_code": lambda x: re.sub(r"\w", "0", x),  # matter
    "setup_payload": lambda x: re.sub(r"\w", "0", x),  # matter
    "mfi_setup_code": lambda x: re.sub(r"\w", "0", x),  # mfi_ for homekit
    "mfi_setup_id": lambda x: re.sub(r"\w", "0", x),
    "mfi_token_token": lambda x: re.sub(r"\w", "0", x),
    "mfi_token_uuid": lambda x: re.sub(r"\w", "0", x),
    "ip": lambda x: x,  # don't redact but keep listed here for dump_devinfo
    # smartcam
    "dev_id": lambda x: "REDACTED_" + x[9::],
    "ext_addr": lambda x: "REDACTED_" + x[9::],
    "device_name": lambda x: "#MASKED_NAME#" if x else "",
    "device_alias": lambda x: "#MASKED_NAME#" if x else "",
    "alias": lambda x: "#MASKED_NAME#" if x else "",  # child info on parent uses alias
    "local_ip": lambda x: x,  # don't redact but keep listed here for dump_devinfo
    # robovac
    "board_sn": lambda _: "000000000000",
    "custom_sn": lambda _: "000000000000",
    "location": lambda x: "#MASKED_NAME#" if x else "",
    "map_data": lambda x: "#SCRUBBED_MAPDATA#" if x else "",
    "map_name": lambda x: "I01BU0tFRF9OQU1FIw==",  # #MASKED_NAME#
    "area_list": _mask_area_list,
    # unknown robovac binary blob in get_device_info
    "cd": lambda x: "I01BU0tFRF9CSU5BUlkj",  # #MASKED_BINARY#
}

# Queries that are known not to work properly when sent as a
# multiRequest. They will not return the `method` key.
FORCE_SINGLE_REQUEST = {
    "getConnectStatus",
    "scanApList",
}


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
        self._query_lock = asyncio.Lock()
        self._multi_request_batch_size = (
            self._transport._config.batch_size or self.DEFAULT_MULTI_REQUEST_BATCH_SIZE
        )
        self._redact_data = True
        self._method_missing_logged = False

    def get_smart_request(self, method: str, params: dict | None = None) -> str:
        """Get a request message as a string."""
        request = {
            "method": method,
            "request_time_milis": round(time.time() * 1000),
            "terminal_uuid": self._terminal_uuid,
        }
        if params:
            request["params"] = params
        return json_dumps(request)

    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Query the device retrying for retry_count on failure."""
        async with self._query_lock:
            return await self._query(request, retry_count)

    async def _query(self, request: str | dict, retry_count: int = 3) -> dict:
        for retry in range(retry_count + 1):
            try:
                return await self._execute_query(
                    request, retry_count=retry, iterate_list_pages=True
                )
            except _ConnectionError as ex:
                if retry == 0:
                    _LOGGER.debug(
                        "Device %s got a connection error, will retry %s times: %s",
                        self._host,
                        retry_count,
                        ex,
                    )
                if retry >= retry_count:
                    _LOGGER.debug("Giving up on %s after %s retries", self._host, retry)
                    raise ex
                continue
            except AuthenticationError as ex:
                await self._transport.reset()
                _LOGGER.debug(
                    "Unable to authenticate with %s, not retrying: %s", self._host, ex
                )
                raise ex
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
                await asyncio.sleep(self.BACKOFF_SECONDS_AFTER_TIMEOUT)
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

    async def _execute_multiple_query(
        self, requests: dict, retry_count: int, iterate_list_pages: bool
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        multi_result: dict[str, Any] = {}
        smart_method = "multipleRequest"

        end = len(requests)
        # The SmartCamProtocol sends requests with a length 1 as a
        # multipleRequest. The SmartProtocol doesn't so will never
        # raise_on_error
        raise_on_error = end == 1

        multi_requests = [
            {"method": method, "params": params} if params else {"method": method}
            for method, params in requests.items()
            if method not in FORCE_SINGLE_REQUEST
        ]

        # Break the requests down as there can be a size limit
        step = self._multi_request_batch_size
        if step == 1:
            # If step is 1 do not send request batches
            for request in multi_requests:
                method = request["method"]
                req = self.get_smart_request(method, request.get("params"))
                resp = await self._transport.send(req)
                self._handle_response_error_code(
                    resp, method, raise_on_error=raise_on_error
                )
                multi_result[method] = resp["result"]
            return multi_result

        for batch_num, i in enumerate(range(0, end, step)):
            requests_step = multi_requests[i : i + step]

            smart_params = {"requests": requests_step}
            smart_request = self.get_smart_request(smart_method, smart_params)
            batch_name = f"multi-request-batch-{batch_num + 1}-of-{int(end / step) + 1}"
            if debug_enabled:
                _LOGGER.debug(
                    "%s %s >> %s",
                    self._host,
                    batch_name,
                    pf(smart_request),
                )
            response_step = await self._transport.send(smart_request)
            if debug_enabled:
                if self._redact_data:
                    data = redact_data(response_step, REDACTORS)
                else:
                    data = response_step
                _LOGGER.debug(
                    "%s %s << %s",
                    self._host,
                    batch_name,
                    pf(data),
                )
            try:
                self._handle_response_error_code(response_step, batch_name)
            except DeviceError as ex:
                # P100 sometimes raises JSON_DECODE_FAIL_ERROR or INTERNAL_UNKNOWN_ERROR
                # on batched request so disable batching
                if (
                    ex.error_code
                    in {
                        SmartErrorCode.JSON_DECODE_FAIL_ERROR,
                        SmartErrorCode.INTERNAL_UNKNOWN_ERROR,
                    }
                    and self._multi_request_batch_size != 1
                ):
                    self._multi_request_batch_size = 1
                    raise _RetryableError(
                        "JSON Decode failure, multi requests disabled"
                    ) from ex
                raise ex

            responses = response_step["result"]["responses"]
            for response in responses:
                # some smartcam devices calls do not populate the method key
                # these should be defined in DO_NOT_SEND_AS_MULTI_REQUEST.
                if not (method := response.get("method")):
                    if not self._method_missing_logged:
                        # Avoid spamming the logs
                        self._method_missing_logged = True
                        _LOGGER.error(
                            "No method key in response for %s, skipping: %s",
                            self._host,
                            response_step,
                        )
                    # These will end up being queried individually
                    continue

                self._handle_response_error_code(
                    response, method, raise_on_error=raise_on_error
                )
                result = response.get("result", None)
                request_params = rp if (rp := requests.get(method)) else None
                if iterate_list_pages and result:
                    await self._handle_response_lists(
                        result, method, request_params, retry_count=retry_count
                    )
                multi_result[method] = result

        # Multi requests don't continue after errors so requery any missing.
        # Will also query individually any DO_NOT_SEND_AS_MULTI_REQUEST.
        for method, params in requests.items():
            if method not in multi_result:
                resp = await self._transport.send(
                    self.get_smart_request(method, params)
                )
                self._handle_response_error_code(
                    resp, method, raise_on_error=raise_on_error
                )
                multi_result[method] = resp.get("result")
        return multi_result

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if isinstance(request, dict):
            if len(request) == 1:
                smart_method = next(iter(request))
                smart_params = request[smart_method]
            else:
                return await self._execute_multiple_query(
                    request, retry_count, iterate_list_pages
                )
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

        self._handle_response_error_code(response_data, smart_method)

        # Single set_ requests do not return a result
        result = response_data.get("result")
        if iterate_list_pages and result:
            await self._handle_response_lists(
                result, smart_method, smart_params, retry_count=retry_count
            )
        return {smart_method: result}

    def _get_list_request(
        self, method: str, params: dict | None, start_index: int
    ) -> dict:
        return {method: {"start_index": start_index}}

    async def _handle_response_lists(
        self,
        response_result: dict[str, Any],
        method: str,
        params: dict | None,
        retry_count: int,
    ) -> None:
        if (
            response_result is None
            or isinstance(response_result, SmartErrorCode)
            or "start_index" not in response_result
            or (list_sum := response_result.get("sum")) is None
        ):
            return

        response_list_name = next(
            iter(
                [
                    key
                    for key in response_result
                    if isinstance(response_result[key], list)
                ]
            )
        )
        while (list_length := len(response_result[response_list_name])) < list_sum:
            request = self._get_list_request(method, params, list_length)
            response = await self._execute_query(
                request,
                retry_count=retry_count,
                iterate_list_pages=False,
            )
            next_batch = response[method]
            # In case the device returns empty lists avoid infinite looping
            if not next_batch[response_list_name]:
                _LOGGER.error(
                    "Device %s returned empty results list for method %s",
                    self._host,
                    method,
                )
                break
            response_result[response_list_name].extend(next_batch[response_list_name])

    def _handle_response_error_code(
        self, resp_dict: dict, method: str, raise_on_error: bool = True
    ) -> None:
        error_code_raw = resp_dict.get("error_code")
        try:
            error_code = SmartErrorCode.from_int(error_code_raw)
        except ValueError:
            _LOGGER.warning(
                "Device %s received unknown error code: %s", self._host, error_code_raw
            )
            error_code = SmartErrorCode.INTERNAL_UNKNOWN_ERROR

        if error_code is SmartErrorCode.SUCCESS:
            return

        if not raise_on_error:
            resp_dict["result"] = error_code
            return

        msg = (
            f"Error querying device: {self._host}: "
            + f"{error_code.name}({error_code.value})"
            + f" for method: {method}"
        )
        if error_code in SMART_RETRYABLE_ERRORS:
            raise _RetryableError(msg, error_code=error_code)
        if error_code in SMART_AUTHENTICATION_ERRORS:
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()


class _ChildProtocolWrapper(SmartProtocol):
    """Protocol wrapper for controlling child devices.

    This is an internal class used to communicate with child devices,
    and should not be used directly.

    This class overrides query() method of the protocol to modify all
    outgoing queries to use ``control_child`` command, and unwraps the
    device responses before returning to the caller.
    """

    def __init__(self, device_id: str, base_protocol: SmartProtocol) -> None:
        self._device_id = device_id
        self._protocol = base_protocol
        self._transport = base_protocol._transport

    def _get_method_and_params_for_request(self, request: dict[str, Any] | str) -> Any:
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
                    if params
                    else {"method": method}
                    for method, params in request.items()
                ]
                smart_params = {"requests": requests}
        else:
            smart_method = request
            smart_params = None

        return smart_method, smart_params

    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Wrap request inside control_child envelope."""
        return await self._query(request, retry_count)

    async def _query(self, request: str | dict, retry_count: int = 3) -> dict:
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
            result = response_data.get("result")
            if result and (multi_responses := result.get("responses")):
                ret_val = {}
                for multi_response in multi_responses:
                    method = multi_response["method"]
                    self._handle_response_error_code(
                        multi_response, method, raise_on_error=False
                    )
                    ret_val[method] = multi_response.get("result")
                return ret_val

            self._handle_response_error_code(response_data, "control_child")

        return {method: result}

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""
