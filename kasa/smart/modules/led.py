"""Module for led controls."""
from typing import Dict

from ..smartmodule import SmartModule


class Led(SmartModule):
    """Implementation of led controls."""

    REQUIRED_COMPONENT = "led"
    QUERY_GETTER_NAME = "get_led_info"

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"led_rule": None}}

    @property
    def mode(self):
        """LED mode setting.

        "always", "never", "night_mode"
        """
        return self.data["led_rule"]

    @property
    def is_on(self):
        """Return current led status."""
        return self.data["led_status"]

    async def set_led(self, enable: bool):
        """Set led."""
        return await self.call("set_led_info", {"led_status": enable})

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

    def __cli_output__(self):
        return f"LED: {self.is_on} (mode: {self.mode})"
