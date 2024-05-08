"""Module for base light effect module."""

from __future__ import annotations

from ..feature import Feature
from ..module import Module


class LedModule(Module):
    """Base interface to represent a LED module."""

    # This needs to implement abstract methods for typing to work with
    # overload get_module(type[ModuleT]) -> ModuleT:
    # https://discuss.python.org/t/add-abstracttype-to-the-typing-module/21996

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device=device,
                container=self,
                name="LED",
                id="led",
                icon="mdi:led-{state}",
                attribute_getter="led",
                attribute_setter="set_led",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    def led(self) -> bool:
        """Return current led status."""
        raise NotImplementedError()

    async def set_led(self, enable: bool) -> None:
        """Set led."""
        raise NotImplementedError()

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        raise NotImplementedError()

    @property
    def data(self):
        """Query to execute during the update cycle."""
        raise NotImplementedError()
