"""Implementation for child devices."""
from typing import Dict

from ..smartmodule import SmartModule


class ChildDeviceModule(SmartModule):
    """Implementation for child devices."""

    REQUIRED_COMPONENT = "child_device"

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        # TODO: There is no need to fetch the component list every time,
        #  so this should be optimized only for the init.
        return {
            "get_child_device_list": None,
            "get_child_device_component_list": None,
        }
