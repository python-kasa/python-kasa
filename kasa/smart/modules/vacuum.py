"""Implementation of vacuum."""

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


class FanSpeed(IntEnum):
    """Fan speed level."""

    Quiet = 1
    Standard = 2
    Turbo = 3
    Max = 4


class Vacuum(SmartModule):
    """Implementation of vacuum support."""

    REQUIRED_COMPONENT = "clean"

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="vacuum_return_home",
                name="Return home",
                container=self,
                attribute_setter="return_home",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="vacuum_start",
                name="Start cleaning",
                container=self,
                attribute_setter="start",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="vacuum_pause",
                name="Pause",
                container=self,
                attribute_setter="pause",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="vacuum_status",
                name="Vacuum status",
                container=self,
                attribute_getter="status",
                category=Feature.Category.Primary,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="battery_level",
                name="Battery level",
                container=self,
                attribute_getter="battery",
                icon="mdi:battery",
                unit_getter=lambda: "%",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                id="vacuum_fan_speed",
                name="Fan speed",
                container=self,
                attribute_getter="fan_speed",
                attribute_setter="set_fan_speed",
                icon="mdi:fan",
                choices_getter=lambda: list([str(speed) for speed in FanSpeed]),
                category=Feature.Category.Primary,
                type=Feature.Type.Choice,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getVacStatus": None,
            "getBatteryInfo": None,
            "getCleanStatus": None,
            "getCleanAttr": {"type": "global"},
        }

    async def start(self) -> dict:
        """Start cleaning."""
        # If we are paused, do not restart cleaning

        if self.status == Status.Paused:
            return await self.resume()

        # TODO: we need to create settings for clean_modes
        return await self.call(
            "setSwitchClean",
            {
                "clean_mode": 0,
                "clean_on": True,
                "clean_order": True,
                "force_clean": False,
            },
        )

    async def pause(self) -> dict:
        """Pause cleaning."""
        return await self.set_pause(True)

    async def resume(self) -> dict:
        """Resume cleaning."""
        return await self.set_pause(False)

    async def set_pause(self, enabled: bool) -> dict:
        """Pause or resume cleaning."""
        return await self.call("setRobotPause", {"pause": enabled})

    async def return_home(self) -> dict:
        """Return home."""
        return await self.set_return_home(True)

    async def set_return_home(self, enabled: bool) -> dict:
        """Return home / pause returning."""
        return await self.call("setSwitchCharge", {"switch_charge": enabled})

    @property
    def fan_speed_preset(self) -> str:
        """Return fan speed preset."""
        return FanSpeed(self.data["getCleanAttr"]["suction"]).name

    async def set_fan_speed_preset(self, speed: str) -> dict:
        """Set fan speed preset."""
        name_to_value = {x.name.lower(): x.value for x in FanSpeed}
        if speed not in name_to_value:
            raise ValueError("Invalid fan speed %s, available %s", speed, name_to_value)
        return await self.call(
            "setCleanAttr", {"suction": name_to_value[speed], "type": "global"}
        )

    @property
    def battery(self) -> int:
        """Return battery level."""
        return self.data["getBatteryInfo"]["battery_percentage"]

    @property
    def _vac_status(self) -> dict:
        """Return vac status container."""
        return self.data["getVacStatus"]

    @property
    def status(self) -> Status:
        """Return current status."""
        if self._vac_status.get("err_status"):
            return Status.Error

        status_code = self._vac_status["status"]
        try:
            return Status(status_code)
        except ValueError:
            _LOGGER.warning("Got unknown status code: %s (%s)", status_code, self.data)
            return Status.Unknown
