"""Screen setting module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class ScreenSetting(SmartModule):
    """Implementation for display rotation."""

    REQUIRED_COMPONENT = "screen_setting"
    QUERY_GETTER_NAME = "get_screen_setting_info"

    def _initialize_features(self):
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="rotate_display",
                name="Rotate display",
                container=self,
                attribute_getter="rotate_display",
                attribute_setter="set_rotate_display",
                type=Feature.Type.Switch,
            )
        )

    @property
    def rotate_display(self) -> bool:
        """Return screen orientation."""
        return self.data["led_rotation"]

    async def set_rotate_display(self, enabled: bool) -> None:
        """Set screen orientation."""
        await self.call("set_screen_setting_info", {"led_rotation": enabled})
