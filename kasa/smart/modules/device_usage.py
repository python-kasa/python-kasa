from ..smartmodule import SmartModule


class DeviceUsage(SmartModule):
    REQUIRED_COMPONENT = "device"
    QUERY_GETTER_NAME = "get_device_usage"
