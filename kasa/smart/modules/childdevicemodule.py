"""Implementation for child devices."""

from __future__ import annotations

from ..smartmodule import SmartModule


class ChildDeviceModule(SmartModule):
    """Implementation for child devices."""

    REQUIRED_COMPONENT = "child_device"
    QUERY_GETTER_NAME = "get_child_device_list"
