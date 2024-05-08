"""Module for led controls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...modules.ledmodule import LedModule as BaseLedModule
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    pass


class LedModule(SmartModule, BaseLedModule):
    """Implementation of led controls."""

    REQUIRED_COMPONENT = "led"
    QUERY_GETTER_NAME = "get_led_info"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"led_rule": None}}

    @property
    def mode(self):
        """LED mode setting.

        "always", "never", "night_mode"
        """
        return self.data["led_rule"]

    @property
    def led(self):
        """Return current led status."""
        return self.data["led_status"]

    async def set_led(self, enable: bool):
        """Set led.

        This should probably be a select with always/never/nightmode.
        """
        rule = "always" if enable else "never"
        return await self.call("set_led_info", dict(self.data, **{"led_rule": rule}))

    @property
    def night_mode_settings(self):
        """Night mode settings."""
        return {
            "start": self.data["start_time"],
            "end": self.data["end_time"],
            "type": self.data["night_mode_type"],
            "sunrise_offset": self.data["sunrise_offset"],
            "sunset_offset": self.data["sunset_offset"],
        }
