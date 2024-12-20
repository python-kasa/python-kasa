"""Base class for IOT module implementations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..exceptions import KasaException
from ..module import Module

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .iotdevice import IotDevice


def _merge_dict(dest: dict, source: dict) -> dict:
    """Update dict recursively."""
    for k, v in source.items():
        if k in dest and type(v) is dict:  # noqa: E721 - only accepts `dict` type
            _merge_dict(dest[k], v)
        else:
            dest[k] = v
    return dest


merge = _merge_dict


class IotModule(Module):
    """Base class implemention for all IOT modules."""

    _device: IotDevice

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Call the given method with the given parameters."""
        return await self._device._query_helper(self._module, method, params)

    def query_for_command(self, query: str, params: dict | None = None) -> dict:
        """Create a request object for the given parameters."""
        return self._device._create_request(self._module, query, params)

    @property
    def estimated_query_response_size(self) -> int:
        """Estimated maximum size of query response.

        The inheriting modules implement this to estimate how large a query response
        will be so that queries can be split should an estimated response be too large
        """
        return 256  # Estimate for modules that don't specify

    @property
    def data(self) -> dict[str, Any]:
        """Return the module specific raw data from the last update."""
        dev = self._device
        q = self.query()

        if not q:
            return dev.sys_info

        if self._module not in dev._last_update:
            raise KasaException(
                f"You need to call update() prior accessing module data"
                f" for '{self._module}'"
            )

        return dev._last_update[self._module]

    @property
    def is_supported(self) -> bool:
        """Return whether the module is supported by the device."""
        if self._module not in self._device._last_update:
            _LOGGER.debug("Initial update, so consider supported: %s", self._module)
            return True

        return "err_code" not in self.data
