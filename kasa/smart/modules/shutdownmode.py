"""Implementation of the shutdown mode module for thermostatic radiator valves.

This is called "Summer Mode" in the Kasa app, and the periodic valve movement
is called "Anti-Blocking".
"""

from __future__ import annotations

from typing import Any

from ...feature import Feature
from ..smartmodule import SmartModule, allow_update_after

VALVE_POSITIONS = ["full_closed", "full_open"]
#: Indexed by the firmware's day value, which accepts 0-6.
#: The Kasa app shows 1 as Monday.
ANTI_BLOCKING_DAYS = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]
#: Firmware rejects anything outside of this range.
ANTI_BLOCKING_MINUTE_RANGE = (0, 1439)


class ShutdownMode(SmartModule):
    """Implementation of the shutdown mode ("Summer Mode")."""

    REQUIRED_COMPONENT = "shutdown_mode"
    QUERY_GETTER_NAME = "get_shutdown_info"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="summer_mode",
                name="Summer mode",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="summer_mode_valve_position",
                name="Summer mode valve position",
                container=self,
                attribute_getter="valve_position",
                attribute_setter="set_valve_position",
                choices_getter=lambda: VALVE_POSITIONS,
                type=Feature.Type.Choice,
                category=Feature.Category.Config,
            )
        )
        # Only seen with version 2 of the component.
        if self.supported_version < 2:
            return
        self._add_feature(
            Feature(
                self._device,
                id="anti_blocking",
                name="Anti-blocking",
                container=self,
                attribute_getter="anti_blocking_enabled",
                attribute_setter="set_anti_blocking_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="anti_blocking_day",
                name="Anti-blocking day",
                container=self,
                attribute_getter="anti_blocking_day",
                attribute_setter="set_anti_blocking_day",
                choices_getter=lambda: ANTI_BLOCKING_DAYS,
                type=Feature.Type.Choice,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="anti_blocking_minute",
                name="Anti-blocking minute of day",
                container=self,
                attribute_getter="anti_blocking_minute",
                attribute_setter="set_anti_blocking_minute",
                range_getter=lambda: ANTI_BLOCKING_MINUTE_RANGE,
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

    @allow_update_after
    async def _set_shutdown_info(self, **changes: Any) -> dict:
        """Write settings.

        Firmware requires enable and mode on every write. They are read first, as
        the module data of a hub child can be up to a day old.
        """
        current = await self.call("get_shutdown_info")
        info = current["get_shutdown_info"]
        params = {"enable": info["enable"], "mode": info["mode"], **changes}
        return await self.call("set_shutdown_info", params)

    @property
    def enabled(self) -> bool:
        """Return True if shutdown mode is enabled.

        This uses the device info, as it is refreshed on every update.
        """
        return "shutdown" in self._device.sys_info["trv_states"]

    async def set_enabled(self, enable: bool) -> dict:
        """Enable or disable shutdown mode."""
        return await self._set_shutdown_info(enable=enable)

    @property
    def valve_position(self) -> str:
        """Return the position the valve holds during shutdown mode."""
        return self.data["mode"]

    async def set_valve_position(self, position: str) -> dict:
        """Set the position the valve holds during shutdown mode."""
        if position not in VALVE_POSITIONS:
            raise ValueError(
                f"Invalid position {position}, must be one of {VALVE_POSITIONS}"
            )
        return await self._set_shutdown_info(mode=position)

    @property
    def anti_blocking_enabled(self) -> bool:
        """Return True if the periodic valve movement is enabled."""
        return self.data["anti_clogging_enable"]

    async def set_anti_blocking_enabled(self, enable: bool) -> dict:
        """Enable or disable the periodic valve movement."""
        return await self._set_shutdown_info(anti_clogging_enable=enable)

    @property
    def anti_blocking_day(self) -> str:
        """Return the name of the day of the valve movement."""
        return ANTI_BLOCKING_DAYS[self.data["anti_clogging_day"]]

    async def set_anti_blocking_day(self, day: str) -> dict:
        """Set the day of the valve movement by name."""
        if day not in ANTI_BLOCKING_DAYS:
            raise ValueError(f"Invalid day {day}, must be one of {ANTI_BLOCKING_DAYS}")
        return await self._set_shutdown_info(
            anti_clogging_day=ANTI_BLOCKING_DAYS.index(day)
        )

    @property
    def anti_blocking_minute(self) -> int:
        """Return the minute of day of the valve movement."""
        return self.data["anti_clogging_min"]

    async def set_anti_blocking_minute(self, minute: float) -> dict:
        """Set the minute of day of the valve movement."""
        low, high = ANTI_BLOCKING_MINUTE_RANGE
        if not low <= minute <= high or minute != int(minute):
            raise ValueError(
                f"Invalid minute {minute}, must be an integer in range [{low},{high}]"
            )
        return await self._set_shutdown_info(anti_clogging_min=int(minute))
