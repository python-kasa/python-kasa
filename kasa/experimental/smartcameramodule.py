"""Base implementation for SMART modules."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..exceptions import SmartErrorCode
from ..smart.smartmodule import SmartModule
from .sslaestransport import SmartErrorCode as ExpSmartErrorCode

if TYPE_CHECKING:
    from .smartcamera import SmartCamera

_LOGGER = logging.getLogger(__name__)


class SmartCameraModule(SmartModule):
    """Base class for SMARTCAMERA modules."""

    NAME: str

    #: Query to execute during the main update cycle
    QUERY_GETTER_NAME: str
    QUERY_MODULE_NAME: str
    QUERY_SECTION_NAMES: str | list[str]

    REGISTERED_MODULES = {}

    _device: SmartCamera

    def __init_subclass__(cls, **kwargs):
        name = getattr(cls, "NAME", cls.__name__)
        _LOGGER.debug("Registering %s", cls)
        cls.REGISTERED_MODULES[name] = cls

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        return {
            self.QUERY_GETTER_NAME: {
                self.QUERY_MODULE_NAME: {"name": self.QUERY_SECTION_NAMES}
            }
        }

    async def call(self, method, module, section, params=None):
        """Call a method.

        Just a helper method.
        """
        if method[:3] == "get":
            return await self._device._query_getter_helper(method, module, section)
        else:
            return await self._device._query_setter_helper(
                method, module, section, params
            )

    @property
    def data(self):
        """Return response data for the module."""
        dev = self._device
        q = self.query()

        if not q:
            return dev.sys_info

        query_resp = dev._last_update.get(self.QUERY_GETTER_NAME, {})
        if isinstance(query_resp, (SmartErrorCode, ExpSmartErrorCode)):
            return None
        return query_resp.get(self.QUERY_MODULE_NAME)

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device.

        Used for parents who report components on the parent that are only available
        on the child or for modules where the device has a pointless component like
        color_temp_range but only supports one value.
        """
        return True

    @property
    def disabled(self) -> bool:
        """Return true if the module received the required data."""
        return not self.data
