"""Module for led controls."""

from __future__ import annotations

from ...feature import Feature
from ...modules.ledmodule import LedModule as BaseLedModule
from ..iotmodule import IotModule


class LedModule(IotModule, BaseLedModule):
    """Implementation of led controls."""

    REQUIRED_COMPONENT = "led"
    QUERY_GETTER_NAME = "get_led_info"

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device=device,
                container=self,
                name="LED",
                icon="mdi:led-{state}",
                attribute_getter="led",
                attribute_setter="set_led",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def mode(self):
        """LED mode setting.

        "always", "never"
        """
        return "always" if self.led else "never"

    @property
    def led(self) -> bool:
        """Return the state of the led."""
        sys_info = self.data
        return bool(1 - sys_info["led_off"])

    async def set_led(self, state: bool):
        """Set the state of the led (night mode)."""
        return await self.call("set_led_off", {"off": int(not state)})
