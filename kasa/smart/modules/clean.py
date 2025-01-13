"""Implementation of vacuum clean module."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Annotated

from ...exceptions import KasaException
from ...feature import Feature
from ...module import FeatureAttribute
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class Status(IntEnum):
    """Status of vacuum."""

    Idle = 0
    Cleaning = 1
    Mapping = 2
    GoingHome = 4
    Charging = 5
    Charged = 6
    Paused = 7
    Undocked = 8
    Error = 100

    UnknownInternal = -1000


class ErrorCode(IntEnum):
    """Error codes for vacuum."""

    Ok = 0
    MainBrushStuck = 3
    WheelBlocked = 4
    DustBinRemoved = 14
    UnableToMove = 15
    LidarBlocked = 16
    UnableToFindDock = 21

    UnknownInternal = -1000


class FanSpeed(IntEnum):
    """Fan speed level."""

    Quiet = 1
    Standard = 2
    Turbo = 3
    Max = 4


class Clean(SmartModule):
    """Implementation of vacuum clean module."""

    REQUIRED_COMPONENT = "clean"
    _error_code = ErrorCode.Ok

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
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
                self._device,
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
                self._device,
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
                self._device,
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
                id="vacuum_error",
                name="Error",
                container=self,
                attribute_getter="error",
                category=Feature.Category.Info,
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
                attribute_getter="fan_speed_preset",
                attribute_setter="set_fan_speed_preset",
                icon="mdi:fan",
                choices_getter=lambda: list(FanSpeed.__members__),
                category=Feature.Category.Primary,
                type=Feature.Type.Choice,
            )
        )

    async def _post_update_hook(self) -> None:
        """Set error code after update."""
        errors = self._vac_status.get("err_status")
        if errors is None or not errors:
            self._error_code = ErrorCode.Ok
            return

        if len(errors) > 1:
            _LOGGER.warning(
                "Multiple error codes, using the first one only: %s", errors
            )

        error = errors.pop(0)
        try:
            self._error_code = ErrorCode(error)
        except ValueError:
            _LOGGER.warning(
                "Unknown error code, please create an issue describing the error: %s",
                error,
            )
            self._error_code = ErrorCode.UnknownInternal

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

        if self.status is Status.Paused:
            return await self.resume()

        try:
            return await self.call(
                "setSwitchClean",
                {
                    "clean_mode": 0,
                    "clean_on": True,
                    "clean_order": True,
                    "force_clean": False,
                },
            )
        except ValueError as ex:
            if "-3001" in ex.args[0]:
                msg = "Unable to start cleaning, battery likely too low"
                raise KasaException(msg) from ex

            raise KasaException("Unable to start cleaning: %s", ex) from ex

    async def pause(self) -> dict:
        """Pause cleaning."""
        if self.status is Status.GoingHome:
            return await self.set_return_home(False)

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
    def error(self) -> ErrorCode:
        """Return error."""
        return self._error_code

    @property
    def fan_speed_preset(self) -> Annotated[str, FeatureAttribute()]:
        """Return fan speed preset."""
        return FanSpeed(self._settings["suction"]).name

    async def set_fan_speed_preset(
        self, speed: str
    ) -> Annotated[dict, FeatureAttribute]:
        """Set fan speed preset."""
        name_to_value = {x.name: x.value for x in FanSpeed}
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
    def _settings(self) -> dict:
        """Return cleaning settings."""
        return self.data["getCleanAttr"]

    @property
    def status(self) -> Status:
        """Return current status."""
        if self._error_code is not ErrorCode.Ok:
            return Status.Error

        status_code = self._vac_status["status"]
        try:
            return Status(status_code)
        except ValueError:
            _LOGGER.warning("Got unknown status code: %s (%s)", status_code, self.data)
            return Status.UnknownInternal
