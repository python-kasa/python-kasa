"""Implementation of vacuum (experimental)."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


class Status(IntEnum):
    """Status of vacuum."""

    Idle = 0
    Cleaning = 1
    GoingHome = 4
    Charging = 5
    Charged = 6
    Paused = 7
    Error = 100
    Unknown = 101


class Vacuum(SmartModule):
    """Implementation of experimental vacuum support."""

    REQUIRED_COMPONENT = "clean"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "return_home",
                "Return home",
                container=self,
                attribute_setter="return_home",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                "start_cleaning",
                "Start cleaning",
                container=self,
                attribute_setter="start",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                "pause",
                "Pause",
                container=self,
                attribute_setter="pause",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                "status",
                "Vacuum state",
                container=self,
                attribute_getter="status",
                category=Feature.Category.Primary,
                type=Feature.Type.Sensor,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"getVacStatus": None}

    async def start(self) -> None:
        """Start cleaning."""
        # If we are paused, do not restart cleaning

        if self.status == Status.Paused:
            return await self.resume()

        # TODO: we need to create settings for clean_modes
        return self.call(
            "setSwitchClean",
            {
                "clean_mode": 0,
                "clean_on": True,
                "clean_order": True,
                "force_clean": False,
            },
        )

    async def pause(self):
        """Pause cleaning."""
        return await self.set_pause(True)

    async def resume(self):
        """Resume cleaning."""
        return await self.set_pause(False)

    async def set_pause(self, enabled: bool) -> None:
        """Pause or resume cleaning."""
        return self.call("setRobotPause", {"pause": enabled})

    async def return_home(self):
        """Return home."""
        return await self.set_return_home(True)

    async def set_return_home(self, enabled: bool) -> None:
        """Return home / pause returning."""
        return self.call("setSwitchCharge", {"switch_charge": enabled})

    @property
    def status(self) -> Status:
        """Return current status."""
        if self.data.get("err_status"):
            return Status.Error
        status_code = self.data["status"]
        try:
            return Status(status_code)
        except Exception:
            _LOGGER.warning("Got unknown status code: %s (%s)", status_code, self.data)
            return Status.Unknown
