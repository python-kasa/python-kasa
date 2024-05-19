"""Module for Device base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import NamedTuple

from ..module import Module


@dataclass
class LightState:
    """Class for smart light preset info."""

    light_on: bool | None = None
    brightness: int | None = None
    hue: int | None = None
    saturation: int | None = None
    color_temp: int | None = None
    transition: bool | None = None


class ColorTempRange(NamedTuple):
    """Color temperature range."""

    min: int
    max: int


class HSV(NamedTuple):
    """Hue-saturation-value."""

    hue: int
    saturation: int
    value: int


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
    def hsv(self) -> HSV:
        """Return the current HSV state of the bulb.

        :return: hue, saturation and value (degrees, %, %)
        """

    @property
    @abstractmethod
    def color_temp(self) -> int:
        """Whether the bulb supports color temperature changes."""

    @property
    @abstractmethod
    def brightness(self) -> int:
        """Return the current brightness in percentage."""

    @abstractmethod
    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> dict:
        """Set new HSV.

        Note, transition is not supported and will be ignored.

        :param int hue: hue in degrees
        :param int saturation: saturation in percentage [0,100]
        :param int value: value in percentage [0, 100]
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_color_temp(
        self, temp: int, *, brightness=None, transition: int | None = None
    ) -> dict:
        """Set the color temperature of the device in kelvin.

        Note, transition is not supported and will be ignored.

        :param int temp: The new color temperature, in Kelvin
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """

    @abstractmethod
    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
