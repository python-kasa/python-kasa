"""Module for lock interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class LockEvent(Enum):
    """Lock event type."""

    Lock = "lock"
    Unlock = "unlock"
    Unknown = "unknown"


class LockMethod(Enum):
    """Method used to lock/unlock."""

    App = "app"
    Manual = "manual"
    Keypad = "keypad"
    NFC = "nfc"
    Fingerprint = "fingerprint"
    HomeKit = "homekit"
    Unknown = "unknown"

    @classmethod
    def from_value(cls, value: str) -> LockMethod:
        """Return lock method from string value."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.Unknown


class Lock(ABC):
    """Interface for lock devices."""

    @property
    @abstractmethod
    def is_locked(self) -> bool:
        """Return True if the device is locked."""

    @property
    @abstractmethod
    def battery_level(self) -> int | None:
        """Return battery level percentage or None if not available."""

    @property
    @abstractmethod
    def auto_lock_enabled(self) -> bool:
        """Return True if auto-lock is enabled."""

    @property
    @abstractmethod
    def auto_lock_time(self) -> int | None:
        """Return auto-lock time in seconds or None if not available."""

    @abstractmethod
    async def lock(self) -> None:
        """Lock the device."""

    @abstractmethod
    async def unlock(self) -> None:
        """Unlock the device."""
