from ..smartmodule import SmartModule


class OnOffGradually(SmartModule):
    """Implementation of gradual on/off."""

    REQUIRED_COMPONENT = "on_off_gradually"
    QUERY_GETTER_NAME = "get_on_off_gradually_info"

    def set_enabled(self, enable: bool):
        """Enable gradual on/off."""
        return self.call("set_on_off_gradually_info", {"enable": enable})

    @property
    def enabled(self) -> bool:
        """Return True if gradual on/off is enabled."""
        return bool(self.data["enable"])

    def __cli_output__(self):
        return f"Gradual on/off enabled: {self.enabled}"
