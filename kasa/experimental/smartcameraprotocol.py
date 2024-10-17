"""Module for SmartCamera Protocol."""

from __future__ import annotations

import logging
from pprint import pformat as pf
from typing import Any

from ..exceptions import DeviceError, KasaException, _RetryableError
from ..json import dumps as json_dumps
from ..smartprotocol import SmartProtocol
from .sslaestransport import (
    SMART_RETRYABLE_ERRORS,
    SmartErrorCode,
)

_LOGGER = logging.getLogger(__name__)


class SmartCameraProtocol(SmartProtocol):
    """Class for SmartCamera Protocol."""

    async def _handle_response_lists(
        self, response_result: dict[str, Any], method, retry_count
    ):
        pass

    def _handle_response_error_code(self, resp_dict: dict, method, raise_on_error=True):
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
        # if error_code in SMART_AUTHENTICATION_ERRORS:
        #    raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if isinstance(request, dict):
            if len(request) == 1:
                method = next(iter(request))
                if method == "multipleRequest":
                    params = request["multipleRequest"]
                    req = {"method": "multipleRequest", "params": params}
                elif method[:3] == "set":
                    params = next(iter(request[method]))
                    req = {
                        "method": method[:3],
                        params: request[method][params],
                    }
                else:
                    return await self._execute_multiple_query(request, retry_count)
            else:
                return await self._execute_multiple_query(request, retry_count)
        else:
            # If method like getSomeThing then module will be some_thing
            method = request
            snake_name = "".join(
                ["_" + i.lower() if i.isupper() else i for i in method]
            ).lstrip("_")
            params = snake_name[4:]
            req = {"method": snake_name[:3], params: {}}

        smart_request = json_dumps(req)
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
            self._handle_response_error_code(response_data, method)

        # TODO need to update handle response lists

        if method[:3] == "set":
            return {}
        if method == "multipleRequest":
            return {method: response_data["result"]}
        return {method: {params: response_data[params]}}


class _ChildCameraProtocolWrapper(SmartProtocol):
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
        if not isinstance(request, dict):
            raise KasaException("Child requests must be dictionaries.")
        requests = []
        for key, val in request.items():
            request = {
                "method": "controlChild",
                "params": {
                    "childControl": {
                        "device_id": self._device_id,
                        "request_data": {key: val},
                    }
                },
            }
            requests.append(request)
        multipleRequest = {"multipleRequest": {"requests": requests}}

        response = await self._protocol.query(multipleRequest, retry_count)
        _LOGGER.info("Multi child request response is %s", response)
        responses = response["multipleRequest"]["responses"]
        response_dict = {}
        for response in responses:
            response_data = response["result"]["response_data"]
            method = response_data["method"]
            self._handle_response_error_code(response, method, raise_on_error=False)
            response_dict[method] = response_data[method]

        return response_dict

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""
