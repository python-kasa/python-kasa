"""Implementation of auto off module."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class AutoOff(SmartModule):
    """Implementation of auto off module."""

    REQUIRED_COMPONENT = "auto_off"
    QUERY_GETTER_NAME = "get_auto_off_config"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="auto_off_enabled",
                name="Auto off enabled",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="auto_off_minutes",
                name="Auto off minutes",
                container=self,
                attribute_getter="delay",
                attribute_setter="set_delay",
                type=Feature.Type.Number,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="auto_off_at",
                name="Auto off at",
                container=self,
                attribute_getter="auto_off_at",
                category=Feature.Category.Info,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"start_index": 0}}

    @property
    def enabled(self) -> bool:
        """Return True if enabled."""
        return self.data["enable"]

    async def set_enabled(self, enable: bool):
        """Enable/disable auto off."""
        return await self.call(
            "set_auto_off_config",
            {"enable": enable, "delay_min": self.data["delay_min"]},
        )

    @property
    def delay(self) -> int:
        """Return time until auto off."""
        return self.data["delay_min"]

    async def set_delay(self, delay: int):
        """Set time until auto off."""
        return await self.call(
            "set_auto_off_config", {"delay_min": delay, "enable": self.data["enable"]}
        )

    @property
    def is_timer_active(self) -> bool:
        """Return True is auto-off timer is active."""
        return self._device.sys_info["auto_off_status"] == "on"

    @property
    def auto_off_at(self) -> datetime | None:
        """Return when the device will be turned off automatically."""
        if not self.is_timer_active:
            return None

        sysinfo = self._device.sys_info

        return self._device.time + timedelta(seconds=sysinfo["auto_off_remain_time"])
