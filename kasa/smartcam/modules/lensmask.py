"""Implementation of lens mask privacy module."""

from __future__ import annotations

import logging

from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class LensMask(SmartCamModule):
    """Implementation of lens mask module."""

    QUERY_GETTER_NAME = "getLensMaskConfig"
    QUERY_MODULE_NAME = "lens_mask"
    QUERY_SECTION_NAMES = "lens_mask_info"

    @property
    def state(self) -> bool:
        """Return the lens mask state."""
        return self.data["lens_mask_info"]["enabled"] == "off"

    async def set_state(self, state: bool) -> dict:
        """Set the lens mask state."""
        params = {"enabled": "on" if state else "off"}
        return await self._device._query_setter_helper(
            "setLensMaskConfig", self.QUERY_MODULE_NAME, "lens_mask_info", params
        )
