"""Module for Device base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple, Optional

from .device import Device

try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel


class ColorTempRange(NamedTuple):
    """Color temperature range."""

    min: int
    max: int


class HSV(NamedTuple):
    """Hue-saturation-value."""

    hue: int
    saturation: int
    value: int


class BulbPreset(BaseModel):
    """Bulb configuration preset."""

    index: int
    brightness: int

    # These are not available for effect mode presets on light strips
    hue: Optional[int]  # noqa: UP007
    saturation: Optional[int]  # noqa: UP007
    color_temp: Optional[int]  # noqa: UP007

    # Variables for effect mode presets
    custom: Optional[int]  # noqa: UP007
    id: Optional[str]  # noqa: UP007
    mode: Optional[int]  # noqa: UP007


class Bulb(Device, ABC):
    """Base class for TP-Link Bulb."""

    def _raise_for_invalid_brightness(self, value):
        if not isinstance(value, int) or not (0 <= value <= 100):
            raise ValueError(f"Invalid brightness value: {value} (valid range: 0-100%)")

    @property
    @abstractmethod
    def is_color(self) -> bool:
        """Whether the bulb supports color changes."""

    @property
    @abstractmethod
    def is_dimmable(self) -> bool:
        """Whether the bulb supports brightness changes."""

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

    @property
    @abstractmethod
    def presets(self) -> list[BulbPreset]:
        """Return a list of available bulb setting presets."""
