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
from .modulemapping import ModuleName

if TYPE_CHECKING:
    from .device import Device as DeviceType  # avoid name clash with Device module
    from .interfaces.led import Led
    from .interfaces.lighteffect import LightEffect
    from .iot import modules as iot
    from .smart import modules as smart

_LOGGER = logging.getLogger(__name__)

ModuleT = TypeVar("ModuleT", bound="Module")


class Module(ABC):
    """Base class implemention for all modules.

    The base classes should implement `query` to return the query they want to be
    executed during the regular update cycle.
    """

    # Common Modules
    LightEffect: Final[ModuleName[LightEffect]] = ModuleName("LightEffectModule")
    Led: Final[ModuleName[Led]] = ModuleName("LedModule")

    # IOT only Modules
    IotAmbientLight: Final[ModuleName[iot.AmbientLight]] = ModuleName("ambient")
    IotAntitheft: Final[ModuleName[iot.Antitheft]] = ModuleName("anti_theft")
    IotCountdown: Final[ModuleName[iot.Countdown]] = ModuleName("countdown")
    IotEmeter: Final[ModuleName[iot.Emeter]] = ModuleName("emeter")
    IotMotion: Final[ModuleName[iot.Motion]] = ModuleName("motion")
    IotSchedule: Final[ModuleName[iot.Schedule]] = ModuleName("schedule")
    IotUsage: Final[ModuleName[iot.Usage]] = ModuleName("usage")
    IotCloud: Final[ModuleName[iot.Cloud]] = ModuleName("cloud")
    IotTime: Final[ModuleName[iot.Time]] = ModuleName("time")

    # SMART only Modules
    Alarm: Final[ModuleName[smart.AlarmModule]] = ModuleName("AlarmModule")
    AutoOff: Final[ModuleName[smart.AutoOffModule]] = ModuleName("AutoOffModule")
    BatterySensor: Final[ModuleName[smart.BatterySensor]] = ModuleName("BatterySensor")
    Brightness: Final[ModuleName[smart.Brightness]] = ModuleName("Brightness")
    ChildDevice: Final[ModuleName[smart.ChildDeviceModule]] = ModuleName(
        "ChildDeviceModule"
    )
    Cloud: Final[ModuleName[smart.CloudModule]] = ModuleName("CloudModule")
    Color: Final[ModuleName[smart.ColorModule]] = ModuleName("ColorModule")
    ColorTemp: Final[ModuleName[smart.ColorTemperatureModule]] = ModuleName(
        "ColorTemperatureModule"
    )
    ContactSensor: Final[ModuleName[smart.ContactSensor]] = ModuleName("ContactSensor")
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
    Time: Final[ModuleName[smart.TimeModule]] = ModuleName("TimeModule")
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
