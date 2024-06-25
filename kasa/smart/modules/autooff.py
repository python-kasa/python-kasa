"""Implementation of auto off module."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class AutoOff(SmartModule):
    """Implementation of auto off module."""

    REQUIRED_COMPONENT = "auto_off"
    QUERY_GETTER_NAME = "get_auto_off_config"

    def _initialize_features(self):
        """Initialize features after the initial update."""
        if not isinstance(self.data, dict):
            _LOGGER.warning(
                "No data available for module, skipping %s: %s", self, self.data
            )
            return

        self._add_feature(
            Feature(
                self._device,
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
                self._device,
                id="auto_off_minutes",
                name="Auto off in",
                container=self,
                attribute_getter="delay",
                attribute_setter="set_delay",
                type=Feature.Type.Number,
                unit="min",  # ha-friendly unit, see UnitOfTime.MINUTES
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="auto_off_at",
                name="Auto off at",
                container=self,
                attribute_getter="auto_off_at",
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
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

    async def _check_supported(self):
        """Additional check to see if the module is supported by the device.

        Parent devices that report components of children such as P300 will not have
        the auto_off_status is sysinfo.
        """
        return "auto_off_status" in self._device.sys_info
