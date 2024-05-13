"""Module for Fan Interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..module import Module


class Fan(Module, ABC):
    """Interface for a Fan."""

    @property
    @abstractmethod
    def fan_speed_level(self) -> int:
        """Return fan speed level."""

    @abstractmethod
    async def set_fan_speed_level(self, level: int):
        """Set fan speed level."""
