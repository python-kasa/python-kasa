"""TP-Link device types."""


from enum import Enum


class DeviceType(Enum):
    """Device type enum."""

    # The values match what the cli has historically used
    Plug = "plug"
    Bulb = "bulb"
    Strip = "strip"
    Switch = "switch"
    StripSocket = "stripsocket"
    Dimmer = "dimmer"
    LightStrip = "lightstrip"
    Sensor = "sensor"
    Hub = "hub"
    Unknown = "unknown"

    @staticmethod
    def from_value(name: str) -> "DeviceType":
        """Return device type from string value."""
        for device_type in DeviceType:
            if device_type.value == name:
                return device_type
        return DeviceType.Unknown


class SupportedDeviceType(Enum):
    """Supported device type enum."""

    Plugs = "Plugs"
    PowerStrips = "Power Strips"
    WallSwitches = "Wall Switches"
    Bulbs = "Bulbs"
    LightStrips = "Light Strips"
    Hubs = "Hubs"
    Sensors = "Sensors"


DEVICE_TYPE_TO_SUPPORTED = {
    DeviceType.Plug: SupportedDeviceType.Plugs,
    DeviceType.Bulb: SupportedDeviceType.Bulbs,
    DeviceType.Strip: SupportedDeviceType.PowerStrips,
    DeviceType.StripSocket: SupportedDeviceType.PowerStrips,
    DeviceType.Dimmer: SupportedDeviceType.WallSwitches,
    DeviceType.Switch: SupportedDeviceType.WallSwitches,
    DeviceType.LightStrip: SupportedDeviceType.LightStrips,
    DeviceType.Sensor: SupportedDeviceType.Sensors,
    DeviceType.Hub: SupportedDeviceType.Hubs,
}
