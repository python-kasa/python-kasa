"""Module for double click enable."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule, allow_update_after


class DoubleClick(SmartModule):
    """Implementation of double click module."""

    REQUIRED_COMPONENT = "double_click"
    QUERY_GETTER_NAME = "get_double_click_info"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="double_click",
                name="Double click",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {}}

    @property
    def enabled(self) -> bool:
        """Return current double click enabled status."""
        return self.data["enable"]

    @allow_update_after
    async def set_enabled(self, enable: bool) -> dict:
        """Set double click enable."""
        return await self.call("set_double_click_info", {"enable": enable})
