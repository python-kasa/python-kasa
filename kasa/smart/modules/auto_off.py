from typing import Dict

from ..smartmodule import SmartModule


class AutoOff(SmartModule):
    REQUIRED_COMPONENT = "auto_off"
    QUERY_GETTER_NAME = "get_auto_off_config"

    def query(self) -> Dict:
        return {self.QUERY_GETTER_NAME: {"start_index": 0}}

    @property
    def enabled(self) -> bool:
        return self.data["enable"]

    def set_enabled(self, enable: bool):
        return self.call("set_auto_off_config", {"enable": enable})

    @property
    def delay(self) -> int:
        return self.data["delay_min"]

    def set_delay(self, delay: int):
        return self.call("set_auto_off_config", {"delay_min": delay})

    def __cli_output__(self):
        return f"Auto off enabled: {self.enabled} (delay: {self.delay}min)"
