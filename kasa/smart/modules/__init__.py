"""Modules for SMART devices."""

from .alarmmodule import AlarmModule
from .autooffmodule import AutoOffModule
from .battery import BatterySensor
from .brightness import Brightness
from .childdevicemodule import ChildDeviceModule
from .childsetup import ChildSetupModule
from .cloudmodule import CloudModule
from .colormodule import ColorModule
from .colortemp import ColorTemperatureModule
from .devicemodule import DeviceModule
from .energymodule import EnergyModule
from .fanmodule import FanModule
from .firmware import Firmware
from .frostprotection import FrostProtectionModule
from .humidity import HumiditySensor
from .ledmodule import LedModule
from .lighteffectmodule import LightEffectModule
from .lighttransitionmodule import LightTransitionModule
from .reportmodule import ReportModule
from .temperature import TemperatureSensor
from .temperaturecontrol import TemperatureControl
from .timemodule import TimeModule
from .triggerlogs import TriggerLogs
from .waterleak import WaterleakSensor

__all__ = [
    "AlarmModule",
    "TimeModule",
    "EnergyModule",
    "DeviceModule",
    "ChildDeviceModule",
    "ChildSetupModule",
    "BatterySensor",
    "HumiditySensor",
    "TemperatureSensor",
    "TemperatureControl",
    "ReportModule",
    "AutoOffModule",
    "LedModule",
    "Brightness",
    "FanModule",
    "Firmware",
    "CloudModule",
    "LightEffectModule",
    "LightTransitionModule",
    "ColorTemperatureModule",
    "ColorModule",
    "WaterleakSensor",
    "FrostProtectionModule",
    "TriggerLogs",
]
