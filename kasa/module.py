"""Base class for all module implementations."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    Final,
    TypeVar,
)

from .exceptions import KasaException
from .feature import Feature
from .modules.modulemapping import ModuleName

if TYPE_CHECKING:
    from .device import Device as DeviceType  # avoid name clash with Device module
    from .iot import modules as iot
    from .modules.ledmodule import LedModule
    from .modules.lighteffectmodule import LightEffectModule
    from .smart import modules as smart

_LOGGER = logging.getLogger(__name__)

ModuleT = TypeVar("ModuleT", bound="Module")


class Module(ABC):
    """Base class implemention for all modules.

    The base classes should implement `query` to return the query they want to be
    executed during the regular update cycle.
    """

    # Common Modules
    LightEffect: Final[ModuleName[LightEffectModule]] = ModuleName("LightEffectModule")
    Led: Final[ModuleName[LedModule]] = ModuleName("LedModule")

    # IOT only Modules
    AmbientLight: Final[ModuleName[iot.AmbientLight]] = ModuleName("AmbientLight")
    Antitheft: Final[ModuleName[iot.Antitheft]] = ModuleName("Antitheft")
    Countdown: Final[ModuleName[iot.Countdown]] = ModuleName("Countdown")
    Emeter: Final[ModuleName[iot.Emeter]] = ModuleName("Emeter")
    Motion: Final[ModuleName[iot.Motion]] = ModuleName("Motion")
    Rule: Final[ModuleName[iot.RuleModule]] = ModuleName("RuleModule")
    Schedule: Final[ModuleName[iot.Schedule]] = ModuleName("Schedule")
    Usage: Final[ModuleName[iot.Usage]] = ModuleName("Usage")

    # TODO Resolve these clashes
    IotCloud: Final[ModuleName[iot.Cloud]] = ModuleName("Cloud")
    IotTime: Final[ModuleName[iot.Time]] = ModuleName("Time")
    Time: Final[ModuleName[smart.TimeModule]] = ModuleName("TimeModule")
    Cloud: Final[ModuleName[smart.CloudModule]] = ModuleName("CloudModule")

    # SMART only Modules
    Alarm: Final[ModuleName[smart.AlarmModule]] = ModuleName("AlarmModule")
    AutoOff: Final[ModuleName[smart.AutoOffModule]] = ModuleName("AutoOffModule")
    BatterySensor: Final[ModuleName[smart.BatterySensor]] = ModuleName("BatterySensor")
    Brightness: Final[ModuleName[smart.Brightness]] = ModuleName("Brightness")
    ChildDevice: Final[ModuleName[smart.ChildDeviceModule]] = ModuleName(
        "ChildDeviceModule"
    )
    Color: Final[ModuleName[smart.ColorModule]] = ModuleName("ColorModule")
    ColorTemp: Final[ModuleName[smart.ColorTemperatureModule]] = ModuleName(
        "ColorTemperatureModule"
    )
    Device: Final[ModuleName[smart.DeviceModule]] = ModuleName("DeviceModule")
    Energy: Final[ModuleName[smart.EnergyModule]] = ModuleName("EnergyModule")
    Fan: Final[ModuleName[smart.FanModule]] = ModuleName("FanModule")
    Firmware: Final[ModuleName[smart.Firmware]] = ModuleName("Firmware")
    FrostProtection: Final[ModuleName[smart.FrostProtectionModule]] = ModuleName(
        "FrostProtectionModule"
    )
    Humidity: Final[ModuleName[smart.HumiditySensor]] = ModuleName("HumiditySensor")
    LightTransition: Final[ModuleName[smart.LightTransitionModule]] = ModuleName(
        "LightTransitionModule"
    )
    Report: Final[ModuleName[smart.ReportModule]] = ModuleName("ReportModule")
    Temperature: Final[ModuleName[smart.TemperatureSensor]] = ModuleName(
        "TemperatureSensor"
    )
    TemperatureSensor: Final[ModuleName[smart.TemperatureControl]] = ModuleName(
        "TemperatureControl"
    )
    WaterleakSensor: Final[ModuleName[smart.WaterleakSensor]] = ModuleName(
        "WaterleakSensor"
    )

    def __init__(self, device: DeviceType, module: str):
        self._device = device
        self._module = module
        self._module_features: dict[str, Feature] = {}

    @abstractmethod
    def query(self):
        """Query to execute during the update cycle.

        The inheriting modules implement this to include their wanted
        queries to the query that gets executed when Device.update() gets called.
        """

    @property
    @abstractmethod
    def data(self):
        """Return the module specific raw data from the last update."""

    def _initialize_features(self):  # noqa: B027
        """Initialize features after the initial update.

        This can be implemented if features depend on module query responses.
        """

    def _add_feature(self, feature: Feature):
        """Add module feature."""
        id_ = feature.id
        if id_ in self._module_features:
            raise KasaException("Duplicate id detected %s" % id_)
        self._module_features[id_] = feature

    def __repr__(self) -> str:
        return (
            f"<Module {self.__class__.__name__} ({self._module})"
            f" for {self._device.host}>"
        )
