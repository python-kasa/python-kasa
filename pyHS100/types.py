import enum


class SmartDeviceException(Exception):
    """
    SmartDeviceException gets raised for errors reported by the plug.
    """
    pass


class DeviceType(enum.Enum):
    Unknown = -1,
    Plug = 0,
    Switch = 1
    Bulb = 2
