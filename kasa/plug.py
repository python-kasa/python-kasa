"""Module for a TPlink device with Led."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .device import Device

_LOGGER = logging.getLogger(__name__)


class Plug(Device, ABC):
    """Base class to represent a plug."""

    @property
    @abstractmethod
    def led(self) -> bool:
        """Return the state of the led."""

    @abstractmethod
    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""


class WallSwitch(Plug, ABC):
    """Base class to represent a Wall Switch."""


class Strip(Plug, ABC):
    """Base class to represent a Power strip."""


class Dimmer(Device, ABC):
    """Base class for devices that are dimmers."""

    @property
    @abstractmethod
    def brightness(self) -> int:
        """Return the current brightness in percentage."""

    @abstractmethod
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> dict:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
