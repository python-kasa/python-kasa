"""Implementation of brightness module."""
from typing import TYPE_CHECKING, Dict

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class Brightness(SmartModule):
    """Implementation of brightness module."""

    REQUIRED_COMPONENT = "brightness"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Brightness",
                container=self,
                attribute_getter="brightness",
                attribute_setter="set_brightness",
                minimum_value=1,
                maximum_value=100,
            )
        )

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        # Brightness is contained in the main device info response.
        return {}

    @property
    def brightness(self):
        """Return current brightness."""
        return self.data["brightness"]

    async def set_brightness(self, brightness: int):
        """Set the brightness."""
        return await self.call("set_device_info", {"brightness": brightness})
