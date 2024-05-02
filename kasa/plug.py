"""Module for a TPlink device with Led."""

import logging
from abc import ABC, abstractmethod

from .device import Device

_LOGGER = logging.getLogger(__name__)


class Led(Device, ABC):
    """Base class to represent a device with an LED."""

    @property
    @abstractmethod
    def is_led(self) -> bool:
        """Return True if the device supports led."""

    @property
    @abstractmethod
    def led(self) -> bool:
        """Return the state of the led."""

    @abstractmethod
    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""


class Plug(Led, ABC):
    """Base class to represent a Plug."""


class WallSwitch(Plug, ABC):
    """Base class to represent a Wall Switch."""


class Strip(Plug, ABC):
    """Base class to represent a Power strip."""
