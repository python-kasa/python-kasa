"""Implementation of auto off module."""
from typing import Dict

from ..smartmodule import SmartModule


class AutoOff(SmartModule):
    """Implementation of auto off module."""

    REQUIRED_COMPONENT = "auto_off"
    QUERY_GETTER_NAME = "get_auto_off_config"

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"start_index": 0}}

    @property
    def enabled(self) -> bool:
        """Return True if enabled."""
        return self.data["enable"]

    def set_enabled(self, enable: bool):
        """Enable/disable auto off."""
        return self.call("set_auto_off_config", {"enable": enable})

    @property
    def delay(self) -> int:
        """Return time until auto off."""
        return self.data["delay_min"]

    def set_delay(self, delay: int):
        """Set time until auto off."""
        return self.call("set_auto_off_config", {"delay_min": delay})

    def __cli_output__(self):
        return f"Auto off enabled: {self.enabled} (delay: {self.delay}min)"
