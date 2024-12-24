"""Interact with a TPLink Light.

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

Lights, like any other supported devices, can be turned on and off:

>>> print(dev.is_on)
>>> await dev.turn_on()
>>> await dev.update()
>>> print(dev.is_on)
True

Get the light module to interact:

>>> light = dev.modules[Module.Light]

You can use the ``has_feature()`` method to check for supported features:

>>> light.has_feature("brightness")
True
>>> light.has_feature("hsv")
True
>>> light.has_feature("color_temp")
True

All known bulbs support changing the brightness:

>>> light.brightness
100
>>> await light.set_brightness(50)
>>> await dev.update()
>>> light.brightness
50

Bulbs supporting color temperature can be queried for the supported range:

>>> if color_temp_feature := light.get_feature("color_temp"):
>>>     print(f"{color_temp_feature.minimum_value}, {color_temp_feature.maximum_value}")
2500, 6500
>>> await light.set_color_temp(3000)
>>> await dev.update()
>>> light.color_temp
3000

Color bulbs can be adjusted by passing hue, saturation and value:

>>> await light.set_hsv(180, 100, 80)
>>> await dev.update()
>>> light.hsv
HSV(hue=180, saturation=100, value=80)


"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Annotated, NamedTuple

from ..module import FeatureAttribute, Module


@dataclass
class LightState:
    """Class for smart light preset info."""

    light_on: bool | None = None
    brightness: int | None = None
    hue: int | None = None
    saturation: int | None = None
    color_temp: int | None = None
    transition: int | None = None


class ColorTempRange(NamedTuple):
    """Color temperature range."""

    min: int
    max: int


class HSV(NamedTuple):
    """Hue-saturation-value."""

    hue: int
    saturation: int
    value: int

    def to_dict(self) -> dict:
        """Return dict represenation."""
        return {"hue": self.hue, "saturation": self.saturation, "value": self.value}


class Light(Module, ABC):
    """Base class for TP-Link Light."""

    @property
    @abstractmethod
    def is_dimmable(self) -> bool:
        """Whether the light supports brightness changes."""

    @property
    @abstractmethod
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""

    @property
    @abstractmethod
    def is_variable_color_temp(self) -> bool:
        """Whether the bulb supports color temperature changes."""

    @property
    @abstractmethod
    def valid_temperature_range(self) -> ColorTempRange:
        """Return the device-specific white temperature range (in Kelvin).

        :return: White temperature range in Kelvin (minimum, maximum)
        """

    @property
    @abstractmethod
    def has_effects(self) -> bool:
        """Return True if the device supports effects."""

    @property
    @abstractmethod
    def hsv(self) -> Annotated[HSV, FeatureAttribute()]:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """

    @property
    @abstractmethod
    def color_temp(self) -> Annotated[int, FeatureAttribute()]:
        """Whether the bulb supports color temperature changes."""

    @property
    @abstractmethod
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness in percentage."""

    @abstractmethod
    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_color_temp(
        self, temp: int, *, brightness: int | None = None, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """

    @property
    @abstractmethod
    def state(self) -> LightState:
        """Return the current light state."""

    @abstractmethod
    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
