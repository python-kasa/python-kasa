"""Module for SmartCamera Protocol."""

from __future__ import annotations

import logging
from pprint import pformat as pf

from ..json import dumps as json_dumps
from ..smartprotocol import SmartProtocol

_LOGGER = logging.getLogger(__name__)


class SmartCameraProtocol(SmartProtocol):
    """Class for SmartCamera Protocol."""

    async def _execute_query(
        self, request: str | dict, *, retry_count: int, iterate_list_pages: bool = True
    ) -> dict:
        debug_enabled = _LOGGER.isEnabledFor(logging.DEBUG)

        if isinstance(request, dict):
            if len(request) == 1:
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
