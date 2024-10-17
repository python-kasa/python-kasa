"""Module for SmartCamera Protocol."""

from __future__ import annotations

import logging
from pprint import pformat as pf
from typing import Any

from ..exceptions import AuthenticationError, DeviceError, _RetryableError
from ..json import dumps as json_dumps
from ..smartprotocol import SmartProtocol
from .sslaestransport import (
    SMART_AUTHENTICATION_ERRORS,
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
        if error_code in SMART_AUTHENTICATION_ERRORS:
            raise AuthenticationError(msg, error_code=error_code)
        raise DeviceError(msg, error_code=error_code)

    async def close(self) -> None:
        """Close the underlying transport."""
        await self._transport.close()

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if isinstance(request, dict):
            if len(request) == 0:
                multi_method = next(iter(request))
                module = next(iter(request[multi_method]))
                req = {
                    "method": multi_method[:3],
                    module: request[multi_method][module],
                }
            else:
                return await self._execute_multiple_query(request, retry_count)
        else:
            # If method like getSomeThing then module will be some_thing
            multi_method = request
            snake_name = "".join(
                ["_" + i.lower() if i.isupper() else i for i in multi_method]
            ).lstrip("_")
            module = snake_name[4:]
            req = {"method": snake_name[:3], module: {}}

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
            self._handle_response_error_code(response_data, multi_method)

        # TODO need to update handle response lists

        if multi_method[:3] == "set":
            return {}
        return {multi_method: {module: response_data[module]}}
