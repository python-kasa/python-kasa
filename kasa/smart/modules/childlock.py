"""Child lock module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class ChildLock(SmartModule):
    """Implementation for child lock."""

    REQUIRED_COMPONENT = "button_and_led"
    QUERY_GETTER_NAME = "getChildLockInfo"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="child_lock",
                name="Child lock",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def enabled(self) -> bool:
        """Return True if child lock is enabled."""
        return self.data["child_lock_status"]

    async def set_enabled(self, enabled: bool) -> dict:
        """Set child lock."""
        return await self.call("setChildLockInfo", {"child_lock_status": enabled})
