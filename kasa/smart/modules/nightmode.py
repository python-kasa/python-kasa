"""Night mode module."""

from ..smartmodule import SmartModule


class NightMode(SmartModule):
    """Implementation for night mode module."""

    REQUIRED_COMPONENT = "night_mode"
    QUERY_GETTER_NAME = "get_night_mode_info"

    # {'get_night_mode_info': {'enable': False,
    # 'effective_time':
    # {'type': 'sunrise_sunset', 'start_min': 1244, 'end_min': 375,
    # 'sunrise_offset': 0, 'sunset_offset': 0}}}

    @property
    def enabled(self) -> bool:
        """Return True if night mode enabled."""
        return self.data["enable"]

    @property
    def type(self) -> str:
        """Return night mode type."""
        return self.data["effective_mode"]["type"]

    @property
    def start_time(self) -> int:
        """Return night mode start time."""
        return self.data["effective_time"]["start_min"]

    @property
    def end_time(self) -> int:
        """Return night mode end time."""
        return self.data["effective_time"]["end_min"]

    @property
    def sunrise_offset(self) -> int:
        """Return sunrise offset."""
        return self.data["effective_time"]["sunrise_offset"]

    @property
    def sunset_offset(self) -> int:
        """Return sunset offset."""
        return self.data["effective_time"]["sunset_offset"]
