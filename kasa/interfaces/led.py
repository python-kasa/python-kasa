"""Module for base light effect module."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..feature import Feature
from ..module import Module


class Led(Module, ABC):
    """Base interface to represent a LED module."""

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device=device,
                container=self,
                name="LED",
                id="led",
                icon="mdi:led",
                attribute_getter="led",
                attribute_setter="set_led",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    @property
    @abstractmethod
    def led(self) -> bool:
        """Return current led status."""

    @abstractmethod
    async def set_led(self, enable: bool) -> None:
        """Set led."""
