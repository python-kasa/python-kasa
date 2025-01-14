"""Module for led controls."""

from __future__ import annotations

from ...interfaces.led import Led as LedInterface
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule


class Led(SmartCamModule, LedInterface):
    """Implementation of led controls."""

    REQUIRED_COMPONENT = "led"
    QUERY_GETTER_NAME = "getLedStatus"
    QUERY_MODULE_NAME = "led"
    QUERY_SECTION_NAMES = "config"

    @property
    def led(self) -> bool:
        """Return current led status."""
        return self.data["config"]["enabled"] == "on"

    @allow_update_after
    async def set_led(self, enable: bool) -> dict:
        """Set led.

        This should probably be a select with always/never/nightmode.
        """
        params = {"enabled": "on"} if enable else {"enabled": "off"}
        return await self.call("setLedStatus", {"led": {"config": params}})
