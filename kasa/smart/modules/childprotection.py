"""Child lock module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class ChildProtection(SmartModule):
    """Implementation for child_protection."""

    REQUIRED_COMPONENT = "child_protection"
    QUERY_GETTER_NAME = "get_child_protection"

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

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def enabled(self) -> bool:
        """Return True if child protection is enabled."""
        return self.data["child_protection"]

    async def set_enabled(self, enabled: bool) -> dict:
        """Set child protection."""
        return await self.call("set_child_protection", {"enable": enabled})
