"""Module for Fan Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Fan(ABC):
    """Interface for a Fan."""

    @property
    @abstractmethod
    def is_fan(self) -> bool:
        """Return True if the device is a fan."""

    @property
    @abstractmethod
    def fan_speed_level(self) -> int:
        """Return fan speed level."""

    @abstractmethod
    async def set_fan_speed_level(self, level: int):
        """Set fan speed level."""
