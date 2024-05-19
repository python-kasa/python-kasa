"""Interface for firmware updates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Callable, Coroutine

from ..module import Module

UpdateResult = bool


class FirmwareDownloadState(ABC):
    """Download state."""

    status: int
    progress: int
    reboot_time: int
    upgrade_time: int
    auto_upgrade: bool


@dataclass
class FirmwareUpdateInfo:
    """Update info status object."""

    update_available: bool | None = None
    current_version: str | None = None
    available_version: str | None = None
    release_date: date | None = None
    release_notes: str | None = None


class Firmware(Module, ABC):
    """Interface to access firmware information and perform updates."""

    @abstractmethod
    async def update_firmware(
        self, *, progress_cb: Callable[[FirmwareDownloadState], Coroutine] | None = None
    ) -> UpdateResult:
        """Perform firmware update.

        This "blocks" until the update process has finished.
        You can set *progress_cb* to get progress updates.
        """

    @abstractmethod
    async def check_for_updates(self) -> FirmwareUpdateInfo:
        """Return firmware update information."""
