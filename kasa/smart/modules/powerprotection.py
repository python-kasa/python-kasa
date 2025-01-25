"""Power protection module."""

from __future__ import annotations

from typing import Annotated

from ...feature import Feature
from ...module import FeatureAttribute
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
                id="power_protection_threshold",
                name="Power protection threshold",
                container=self,
                attribute_getter="_threshold_or_zero",
                attribute_setter="_set_threshold_auto_enable",
                unit_getter=lambda: "W",
                type=Feature.Type.Number,
                range_getter=lambda: (0, self._max_power),
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"get_protection_power": {}, "get_max_power": {}}

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

    async def set_enabled(self, enabled: bool, *, threshold: int | None = None) -> dict:
        """Set power protection enabled.

        If power protection has never been enabled before the threshold will
        be 0 so if threshold is not provided it will be set to half the max.
        """
        if threshold is None and enabled and self.protection_threshold == 0:
            threshold = int(self._max_power / 2)

        if threshold and (threshold < 0 or threshold > self._max_power):
            raise ValueError(
                "Threshold out of range: %s (%s)", threshold, self.protection_threshold
            )

        params = {**self.data["get_protection_power"], "enabled": enabled}
        if threshold is not None:
            params["protection_power"] = threshold
        return await self.call("set_protection_power", params)

    async def _set_threshold_auto_enable(self, threshold: int) -> dict:
        """Set power protection and enable."""
        if threshold == 0:
            return await self.set_enabled(False)
        else:
            return await self.set_enabled(True, threshold=threshold)

    @property
    def _threshold_or_zero(self) -> int:
        """Get power protection threshold. 0 if not enabled."""
        return self.protection_threshold if self.enabled else 0

    @property
    def _max_power(self) -> int:
        """Return max power."""
        return self.data["get_max_power"]["max_power"]

    @property
    def protection_threshold(
        self,
    ) -> Annotated[int, FeatureAttribute("power_protection_threshold")]:
        """Return protection threshold in watts."""
        # If never configured, there is no value set.
        return self.data["get_protection_power"].get("protection_power", 0)

    async def set_protection_threshold(self, threshold: int) -> dict:
        """Set protection threshold."""
        if threshold < 0 or threshold > self._max_power:
            raise ValueError(
                "Threshold out of range: %s (%s)", threshold, self.protection_threshold
            )

        params = {
            **self.data["get_protection_power"],
            "protection_power": threshold,
        }
        return await self.call("set_protection_power", params)

    async def _check_supported(self) -> bool:
        """Return True if module is supported.

        This is needed, as strips like P304M report the status only for children.
        """
        return "power_protection_status" in self._device.sys_info
