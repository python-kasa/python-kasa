"""Implementation for child devices."""

from ..smartmodule import SmartModule


class ChildDeviceModule(SmartModule):
    """Implementation for child devices."""

    REQUIRED_COMPONENT = "child_device"
    QUERY_GETTER_NAME = "get_child_device_list"
