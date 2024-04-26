"""Implementation of fan_control module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...exceptions import KasaException
from ...fan import FanState
from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class FanModule(SmartModule):
    """Implementation of fan_control module."""

    REQUIRED_COMPONENT = "fan_control"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)

        self._add_feature(
            Feature(
                device,
                "Fan speed level",
                container=self,
                attribute_getter="fan_speed_level",
                attribute_setter="set_fan_speed_level",
                icon="mdi:fan",
                type=Feature.Type.Number,
                minimum_value=1,
                maximum_value=4,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                "Fan sleep mode",
                container=self,
                attribute_getter="sleep_mode",
                attribute_setter="set_sleep_mode",
                icon="mdi:sleep",
                type=Feature.Type.Switch,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def fan_state(self) -> FanState:
        """Return fan state."""
        return FanState(
            is_on=self.data["device_on"], speed_level=self.data["fan_speed_level"]
        )

    async def set_fan_state(
        self, fan_on: bool | None = None, speed_level: int | None = None
    ):
        """Set fan state."""
        if fan_on is None and speed_level is None:
            raise KasaException("Must provide at least one state.")
        if speed_level and (speed_level < 1 or speed_level > 4):
            raise ValueError("Invalid speed level, should be in range 1-4.")
        params: dict[str, bool | int] = {}
        if fan_on is not None:
            params["device_on"] = fan_on
        if speed_level is not None:
            params["fan_speed_level"] = speed_level
        return await self.call("set_device_info", params)

    @property
    def fan_speed_level(self) -> int:
        """Return fan speed level."""
        return self.data["fan_speed_level"]

    async def set_fan_speed_level(self, level: int):
        """Set fan speed level."""
        if level < 1 or level > 4:
            raise ValueError("Invalid level, should be in range 1-4.")
        return await self.call("set_device_info", {"fan_speed_level": level})

    @property
    def sleep_mode(self) -> bool:
        """Return sleep mode status."""
        return self.data["fan_sleep_mode_on"]

    async def set_sleep_mode(self, on: bool):
        """Set sleep mode."""
        return await self.call("set_device_info", {"fan_sleep_mode_on": on})

    async def _check_supported(self):
        """Is the module available on this device."""
        return "fan_speed_level" in self.data
