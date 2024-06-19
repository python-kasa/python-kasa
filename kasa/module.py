"""Interact with modules.

Modules are implemented by devices to encapsulate sets of functionality like
Light, AutoOff, Firmware etc.

>>> from kasa import Discover, Module
>>>
>>> dev = await Discover.discover_single(
>>>     "127.0.0.3",
>>>     username="user@example.com",
>>>     password="great_password"
>>> )
>>> await dev.update()
>>> print(dev.alias)
Living Room Bulb

To see whether a device supports functionality check for the existence of the module:

>>> if light := dev.modules.get("Light"):
>>>     print(light.hsv)
HSV(hue=0, saturation=100, value=100)

If you know or expect the module to exist you can access by index:

>>> light_preset = dev.modules["LightPreset"]
>>> print(light_preset.preset_list)
['Not set', 'Light preset 1', 'Light preset 2', 'Light preset 3',\
 'Light preset 4', 'Light preset 5', 'Light preset 6', 'Light preset 7']

Modules support typing via the Module names in Module:

>>> from typing_extensions import reveal_type, TYPE_CHECKING
>>> light_effect = dev.modules.get("LightEffect")
>>> light_effect_typed = dev.modules.get(Module.LightEffect)
>>> if TYPE_CHECKING:
>>>     reveal_type(light_effect)  # Static checker will reveal: str
>>>     reveal_type(light_effect_typed)  # Static checker will reveal: LightEffect

"""

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
    from . import interfaces
    from .device import Device
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
    Energy: Final[ModuleName[interfaces.Energy]] = ModuleName("Energy")
    Fan: Final[ModuleName[interfaces.Fan]] = ModuleName("Fan")
    LightEffect: Final[ModuleName[interfaces.LightEffect]] = ModuleName("LightEffect")
    Led: Final[ModuleName[interfaces.Led]] = ModuleName("Led")
    Light: Final[ModuleName[interfaces.Light]] = ModuleName("Light")
    LightPreset: Final[ModuleName[interfaces.LightPreset]] = ModuleName("LightPreset")

    # IOT only Modules
    IotAmbientLight: Final[ModuleName[iot.AmbientLight]] = ModuleName("ambient")
    IotAntitheft: Final[ModuleName[iot.Antitheft]] = ModuleName("anti_theft")
    IotCountdown: Final[ModuleName[iot.Countdown]] = ModuleName("countdown")
    IotMotion: Final[ModuleName[iot.Motion]] = ModuleName("motion")
    IotSchedule: Final[ModuleName[iot.Schedule]] = ModuleName("schedule")
    IotUsage: Final[ModuleName[iot.Usage]] = ModuleName("usage")
    IotCloud: Final[ModuleName[iot.Cloud]] = ModuleName("cloud")
    IotTime: Final[ModuleName[iot.Time]] = ModuleName("time")

    # SMART only Modules
    Alarm: Final[ModuleName[smart.Alarm]] = ModuleName("Alarm")
    AutoOff: Final[ModuleName[smart.AutoOff]] = ModuleName("AutoOff")
    BatterySensor: Final[ModuleName[smart.BatterySensor]] = ModuleName("BatterySensor")
    Brightness: Final[ModuleName[smart.Brightness]] = ModuleName("Brightness")
    ChildDevice: Final[ModuleName[smart.ChildDevice]] = ModuleName("ChildDevice")
    Cloud: Final[ModuleName[smart.Cloud]] = ModuleName("Cloud")
    Color: Final[ModuleName[smart.Color]] = ModuleName("Color")
    ColorTemperature: Final[ModuleName[smart.ColorTemperature]] = ModuleName(
        "ColorTemperature"
    )
    ContactSensor: Final[ModuleName[smart.ContactSensor]] = ModuleName("ContactSensor")
    DeviceModule: Final[ModuleName[smart.DeviceModule]] = ModuleName("DeviceModule")
    Firmware: Final[ModuleName[smart.Firmware]] = ModuleName("Firmware")
    FrostProtection: Final[ModuleName[smart.FrostProtection]] = ModuleName(
        "FrostProtection"
    )
    HumiditySensor: Final[ModuleName[smart.HumiditySensor]] = ModuleName(
        "HumiditySensor"
    )
    LightTransition: Final[ModuleName[smart.LightTransition]] = ModuleName(
        "LightTransition"
    )
    ReportMode: Final[ModuleName[smart.ReportMode]] = ModuleName("ReportMode")
    TemperatureSensor: Final[ModuleName[smart.TemperatureSensor]] = ModuleName(
        "TemperatureSensor"
    )
    TemperatureControl: Final[ModuleName[smart.TemperatureControl]] = ModuleName(
        "TemperatureControl"
    )
    Time: Final[ModuleName[smart.Time]] = ModuleName("Time")
    WaterleakSensor: Final[ModuleName[smart.WaterleakSensor]] = ModuleName(
        "WaterleakSensor"
    )

    def __init__(self, device: Device, module: str):
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
        It will only be called once per module and will always be called
        after *_post_update_hook* has been called for every device module and its
        children's modules.
        """

    def _post_update_hook(self):  # noqa: B027
        """Perform actions after a device update.

        This can be implemented if a module needs to perform actions each time
        the device has updated like generating collections for property access.
        It will be called after every update and will be called prior to
        *_initialize_features* on the first update.
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
