"""Interface for firmware updates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable

UpdateResult = bool


@dataclass
class FirmwareUpdate:
    """Update info status object."""

    update_available: bool | None = None
    current_version: str | None = None
    available_version: str | None = None
    release_date: date | None = None
    release_notes: str | None = None


class Firmware(ABC):
    """Interface to access firmware information and perform updates."""

    @abstractmethod
    async def update_firmware(
        self, *, progress_cb: Callable[[Any, Any], Awaitable]
    ) -> UpdateResult:
        """Perform firmware update.

        This "blocks" until the update process has finished.
        You can set *progress_cb* to get progress updates.
        """
        raise NotImplementedError

    @abstractmethod
    async def check_for_updates(self) -> FirmwareUpdate:
        """Return information about available updates."""
        raise NotImplementedError
