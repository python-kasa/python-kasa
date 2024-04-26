"""Module for Fan Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FanState:
    """Class to represent the current state of the Fan."""

    is_on: bool
    speed_level: int


class Fan(ABC):
    """Interface for a Fan."""

    @property
    @abstractmethod
    def is_fan(self) -> bool:
        """Return True if the device is a fan."""

    @property
    @abstractmethod
    def fan_state(self) -> FanState:
        """Return fan state."""

    @abstractmethod
    async def set_fan_state(self, fan_on: bool | None, speed_level: int | None):
        """Set fan state."""

    @property
    @abstractmethod
    def fan_speed_level(self) -> int:
        """Return fan speed level."""

    @abstractmethod
    async def set_fan_speed_level(self, level: int):
        """Set fan speed level."""
