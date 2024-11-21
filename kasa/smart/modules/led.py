"""Module for led controls."""

from __future__ import annotations

from ...interfaces.led import Led as LedInterface
from ..smartmodule import SmartModule, allow_update_after


class Led(SmartModule, LedInterface):
    """Implementation of led controls."""

    REQUIRED_COMPONENT = "led"
    QUERY_GETTER_NAME = "get_led_info"
    # Led queries can cause device to crash on P100
    MINIMUM_UPDATE_INTERVAL_SECS = 60 * 60

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: None}

    @property
    def mode(self) -> str:
        """LED mode setting.

        "always", "never", "night_mode"
        """
        return self.data["led_rule"]

    @property
    def led(self) -> bool:
        """Return current led status."""
        return self.data["led_rule"] != "never"

    @allow_update_after
    async def set_led(self, enable: bool) -> dict:
        """Set led.

        This should probably be a select with always/never/nightmode.
        """
        rule = "always" if enable else "never"
        return await self.call("set_led_info", dict(self.data, **{"led_rule": rule}))

    @property
    def night_mode_settings(self) -> dict:
        """Night mode settings."""
        return {
            "start": self.data["start_time"],
            "end": self.data["end_time"],
            "type": self.data["night_mode_type"],
            "sunrise_offset": self.data["sunrise_offset"],
            "sunset_offset": self.data["sunset_offset"],
        }
