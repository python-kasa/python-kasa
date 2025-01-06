"""Module for SmartCamProtocol."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pprint import pformat as pf
from typing import Any, cast

from ..exceptions import (
    AuthenticationError,
    DeviceError,
    KasaException,
    _RetryableError,
)
from ..json import dumps as json_dumps
from ..transports.sslaestransport import (
    SMART_AUTHENTICATION_ERRORS,
    SMART_RETRYABLE_ERRORS,
    SmartErrorCode,
)
from .smartprotocol import SmartProtocol

_LOGGER = logging.getLogger(__name__)

# List of getMethodNames that should be sent as {"method":"do"}
# https://md.depau.eu/s/r1Ys_oWoP#Modules
GET_METHODS_AS_DO = {
    "getSdCardFormatStatus",
    "getConnectionType",
    "getUserID",
    "getP2PSharePassword",
    "getAESEncryptKey",
    "getFirmwareAFResult",
    "getWhitelampStatus",
}


@dataclass
class SingleRequest:
    """Class for returning single request details from helper functions."""

    method_type: str
    method_name: str
    param_name: str
    request: dict[str, Any]


class SmartCamProtocol(SmartProtocol):
    """Class for SmartCam Protocol."""

    def _get_list_request(
        self, method: str, params: dict | None, start_index: int
    ) -> dict:
        # All smartcam requests have params
        params = cast(dict, params)
        module_name = next(iter(params))
        return {method: {module_name: {"start_index": start_index}}}

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

    @staticmethod
    def _get_smart_camera_single_request(
        request: dict[str, dict[str, Any]],
    ) -> SingleRequest:
        method = next(iter(request))
        if method == "multipleRequest":
            method_type = "multi"
            params = request["multipleRequest"]
            req = {"method": "multipleRequest", "params": params}
            return SingleRequest("multi", "multipleRequest", "", req)

        param = next(iter(request[method]))
        method_type = method
        req = {
            "method": method,
            param: request[method][param],
        }
        return SingleRequest(method_type, method, param, req)

    @staticmethod
    def _make_snake_name(name: str) -> str:
        """Convert camel or pascal case to snake name."""
        sn = "".join(["_" + i.lower() if i.isupper() else i for i in name]).lstrip("_")
        return sn

    @staticmethod
    def _make_smart_camera_single_request(
        request: str,
    ) -> SingleRequest:
        """Make a single request given a method name and no params.

        If method like getSomeThing then module will be some_thing.
        """
        method = request
        method_type = request[:3]
        snake_name = SmartCamProtocol._make_snake_name(request)
        param = snake_name[4:]
        if (
            (short_method := method[:3])
            and short_method in {"get", "set"}
            and method not in GET_METHODS_AS_DO
        ):
            method_type = short_method
            param = snake_name[4:]
        else:
            method_type = "do"
            param = snake_name
        req = {"method": method_type, param: {}}
        return SingleRequest(method_type, method, param, req)

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)
        if isinstance(request, dict):
            method = next(iter(request))
            if len(request) == 1 and method in {"get", "set", "do", "multipleRequest"}:
                single_request = self._get_smart_camera_single_request(request)
            else:
                return await self._execute_multiple_query(
                    request, retry_count, iterate_list_pages
                )
        else:
            single_request = self._make_smart_camera_single_request(request)

        smart_request = json_dumps(single_request.request)
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

        if "error_code" in response_data:
            # H200 does not return an error code
            self._handle_response_error_code(response_data, single_request.method_name)
        # Requests that are invalid and raise PROTOCOL_FORMAT_ERROR when sent
        # as a multipleRequest will return {} when sent as a single request.
        if single_request.method_type == "get" and (
            not (section := next(iter(response_data))) or response_data[section] == {}
        ):
            raise DeviceError(
                f"No results for get request {single_request.method_name}"
            )

        # TODO need to update handle response lists

        if single_request.method_type == "do":
            return {single_request.method_name: response_data}
        if single_request.method_type == "set":
            return {}
        if single_request.method_type == "multi":
            return {single_request.method_name: response_data["result"]}
        return {
            single_request.method_name: {
                single_request.param_name: response_data[single_request.param_name]
            }
        }


class _ChildCameraProtocolWrapper(SmartProtocol):
    """Protocol wrapper for controlling child devices.

    This is an internal class used to communicate with child devices,
    and should not be used directly.

    This class overrides query() method of the protocol to modify all
    outgoing queries to use ``controlChild`` command, and unwraps the
    device responses before returning to the caller.
    """

    def __init__(self, device_id: str, base_protocol: SmartProtocol) -> None:
        self._device_id = device_id
        self._protocol = base_protocol
        self._transport = base_protocol._transport

    async def query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Wrap request inside controlChild envelope."""
        return await self._query(request, retry_count)

    async def _query(self, request: str | dict, retry_count: int = 3) -> dict:
        """Wrap request inside controlChild envelope."""
        if not isinstance(request, dict):
            raise KasaException("Child requests must be dictionaries.")
        requests = []
        methods = []
        for key, val in request.items():
            request = {
                "method": "controlChild",
                "params": {
                    "childControl": {
                        "device_id": self._device_id,
                        "request_data": {"method": key, "params": val},
                    }
                },
            }
            methods.append(key)
            requests.append(request)

        multipleRequest = {"multipleRequest": {"requests": requests}}

        response = await self._protocol.query(multipleRequest, retry_count)

        responses = response["multipleRequest"]["responses"]
        response_dict = {}

        # Raise errors for single calls
        raise_on_error = len(requests) == 1

        for index_id, response in enumerate(responses):
            response_data = response["result"]["response_data"]
            method = methods[index_id]
            self._handle_response_error_code(
                response_data, method, raise_on_error=raise_on_error
            )
            response_dict[method] = response_data.get("result")

        return response_dict

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""
