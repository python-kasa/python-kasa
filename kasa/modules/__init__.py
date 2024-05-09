"""Sub Package for device family independant modules."""

from ..iot import modules as iot
from ..smart import modules as smart
from .ledmodule import LedModule
from .lighteffectmodule import LightEffectModule
from .modulemapping import ModuleName

# Common Modules
LIGHT_EFFECT: ModuleName["LightEffectModule"] = ModuleName("LightEffectModule")
LED: ModuleName["LedModule"] = ModuleName("LedModule")

# IOT only Modules
AMBIENT_LIGHT: ModuleName["iot.AmbientLight"] = ModuleName("AmbientLight")
ANTITHEFT: ModuleName["iot.Antitheft"] = ModuleName("Antitheft")
CLOUD: ModuleName["iot.Cloud"] = ModuleName("Cloud")
COUNTDOWN: ModuleName["iot.Countdown"] = ModuleName("Countdown")
EMETER: ModuleName["iot.Emeter"] = ModuleName("Emeter")
MOTION: ModuleName["iot.Motion"] = ModuleName("Motion")
RULE: ModuleName["iot.RuleModule"] = ModuleName("RuleModule")
SCHEDULE: ModuleName["iot.Schedule"] = ModuleName("Schedule")
TIME: ModuleName["iot.Time"] = ModuleName("Time")
USAGE: ModuleName["iot.Usage"] = ModuleName("Usage")

# SMART only Modules
ALARM: ModuleName["smart.AlarmModule"] = ModuleName("AlarmModule")
AUTO_OFF: ModuleName["smart.AutoOffModule"] = ModuleName("AutoOffModule")
BATTERY_SENSOR: ModuleName["smart.BatterySensor"] = ModuleName("BatterySensor")
BRIGHTNESS: ModuleName["smart.Brightness"] = ModuleName("Brightness")
CHILD_DEVICE: ModuleName["smart.ChildDeviceModule"] = ModuleName("ChildDeviceModule")
COLOR: ModuleName["smart.ColorModule"] = ModuleName("ColorModule")
COLOR_TEMP: ModuleName["smart.ColorTemperatureModule"] = ModuleName(
    "ColorTemperatureModule"
)
DEVICE: ModuleName["smart.DeviceModule"] = ModuleName("DeviceModule")
ENERGY: ModuleName["smart.EnergyModule"] = ModuleName("EnergyModule")
FAN: ModuleName["smart.FanModule"] = ModuleName("FanModule")
FIRMWARE: ModuleName["smart.Firmware"] = ModuleName("Firmware")
FROST_PROTECTION: ModuleName["smart.FrostProtectionModule"] = ModuleName(
    "FrostProtectionModule"
)
HUMIDITY: ModuleName["smart.HumiditySensor"] = ModuleName("HumiditySensor")
LIGHT_TRANSITION: ModuleName["smart.LightTransitionModule"] = ModuleName(
    "LightTransitionModule"
)
REPORT: ModuleName["smart.ReportModule"] = ModuleName("ReportModule")
TEMPERATURE: ModuleName["smart.TemperatureSensor"] = ModuleName("TemperatureSensor")
TEMPERATURE_SENSOR: ModuleName["smart.TemperatureControl"] = ModuleName(
    "TemperatureControl"
)
WATERLEAK_SENSOR: ModuleName["smart.WaterleakSensor"] = ModuleName("WaterleakSensor")

# TODO Resolve these clashes
TIME_SMART: ModuleName["smart.TimeModule"] = ModuleName("TimeModule")
CLOUD_SMART: ModuleName["smart.CloudModule"] = ModuleName("CloudModule")

__all__ = [
    # Common modules
    "LightEffectModule",
    "LedModule",
    # IOT only modules
    "AMBIENT_LIGHT",
    "ANTITHEFT",
    "CLOUD",
    "COUNTDOWN",
    "EMETER",
    "MOTION",
    "RULE",
    "SCHEDULE",
    "TIME",
    "USAGE",
    # SMART only modules
    "ALARM",
    "AUTO_OFF",
    "BATTERY_SENSOR",
    "BRIGHTNESS",
    "CHILD_DEVICE",
    "COLOR",
    "COLOR_TEMP",
    "DEVICE",
    "ENERGY",
    "FAN",
    "FIRMWARE",
    "FROST_PROTECTION",
    "HUMIDITY",
    "LIGHT_TRANSITION",
    "REPORT",
    "TEMPERATURE",
    "TEMPERATURE_SENSOR",
    "WATERLEAK_SENSOR",
    # Names to be resolved
    "TIME_SMART",
    "CLOUD_SMART",
]
