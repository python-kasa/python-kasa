from typing import Dict
from ..smartmodule import SmartModule


class DeviceModule(SmartModule):
    REQUIRED_COMPONENT = "device"

    def query(self) -> Dict:
        query = {
            "get_device_info": None,
        }
        # Device usage is not available on older firmware versions
        if self._device._components[self.REQUIRED_COMPONENT] >= 2:
            query["get_device_usage"] = None

        return query