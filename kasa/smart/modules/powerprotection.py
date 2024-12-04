"""Power protection module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class PowerProtection(SmartModule):
    """Implementation for power_protection."""

    REQUIRED_COMPONENT = "power_protection"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="overloaded",
                name="Overloaded",
                container=self,
                attribute_getter="overloaded",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                id="power_protection_enabled",
                name="Power protection enabled",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                id="power_protection_threshold",
                name="Power protection threshold",
                container=self,
                attribute_getter="protection_threshold",
                attribute_setter="set_protection_threshold",
                unit_getter=lambda: "W",
                type=Feature.Type.Number,
                range_getter="protection_threshold_range",
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"get_protection_power": None, "get_max_power": None}

    @property
    def overloaded(self) -> bool:
        """Return True is power protection has been triggered.

        This value remains True until the device is turned on again.
        """
        return self._device.sys_info["power_protection_status"] == "overloaded"

    @property
    def enabled(self) -> bool:
        """Return True if child protection is enabled."""
        return self.data["get_protection_power"]["enabled"]

    async def set_enabled(self, enabled: bool) -> dict:
        """Set child protection."""
        params = {**self.data["get_protection_power"], "enabled": enabled}
        return await self.call("set_protection_power", params)

    @property
    def protection_threshold_range(self) -> tuple[int, int]:
        """Return threshold range."""
        return 0, self.data["get_max_power"]["max_power"]

    @property
    def protection_threshold(self) -> int:
        """Return protection threshold in watts."""
        # If never configured, there is no value set.
        return self.data["get_protection_power"].get("protection_power", 0)

    async def set_protection_threshold(self, threshold: int) -> dict:
        """Set protection threshold."""
        if threshold < 0 or threshold > self.protection_threshold_range[1]:
            raise ValueError(
                "Threshold out of range: %s (%s)", threshold, self.protection_threshold
            )

        params = {
            **self.data["get_protection_power"],
            "protection_power": threshold,
        }
        return await self.call("set_protection_power", params)
