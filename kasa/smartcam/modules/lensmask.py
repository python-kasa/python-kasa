"""Implementation of lens mask privacy module."""

from __future__ import annotations

import logging

from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class LensMask(SmartCamModule):
    """Implementation of lens mask module."""

    REQUIRED_COMPONENT = "lensMask"

    QUERY_GETTER_NAME = "getLensMaskConfig"
    QUERY_MODULE_NAME = "lens_mask"
    QUERY_SECTION_NAMES = "lens_mask_info"

    @property
    def enabled(self) -> bool:
        """Return the lens mask state."""
        return self.data["lens_mask_info"]["enabled"] == "on"

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set the lens mask state."""
        params = {"enabled": "on" if enable else "off"}
        return await self._device._query_setter_helper(
            "setLensMaskConfig", self.QUERY_MODULE_NAME, "lens_mask_info", params
        )
