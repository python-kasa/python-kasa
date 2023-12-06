"""TP-Link device types."""


from enum import Enum


class DeviceType(Enum):
    """Device type enum."""

    # The values match what the cli has historically used
    Plug = "plug"
    Bulb = "bulb"
    Strip = "strip"
    StripSocket = "stripsocket"
    Dimmer = "dimmer"
    LightStrip = "lightstrip"
    TapoPlug = "tapoplug"
    TapoBulb = "tapobulb"
    Unknown = "unknown"

    @staticmethod
    def from_value(name: str) -> "DeviceType":
        """Return device type from string value."""
        for device_type in DeviceType:
            if device_type.value == name:
                return device_type
        return DeviceType.Unknown
