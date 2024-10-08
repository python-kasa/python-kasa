"""Module for time interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, tzinfo

from ..module import Module


class Time(Module, ABC):
    """Base class for tplink time module."""

    @property
    @abstractmethod
    def time(self) -> datetime:
        """Return timezone aware current device time."""

    @property
    @abstractmethod
    def timezone(self) -> tzinfo:
        """Return current timezone."""

    @abstractmethod
    async def set_time(self, dt: datetime) -> dict:
        """Set the device time."""
