"""Module for base light effect module."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..feature import Feature
from ..module import Module


class Brightness(Module, ABC):
    """Base interface to represent a Brightness module."""

    BRIGHTNESS_MIN = 0
    BRIGHTNESS_MAX = 100

    def _initialize_features(self):
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="brightness",
                name="Brightness",
                container=self,
                attribute_getter="brightness",
                attribute_setter="set_brightness",
                minimum_value=self.BRIGHTNESS_MIN,
                maximum_value=self.BRIGHTNESS_MAX,
                type=Feature.Type.Number,
                category=Feature.Category.Primary,
            )
        )

    @property
    @abstractmethod
    def brightness(self) -> int:
        """Return current brightness in percentage."""

    @abstractmethod
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> None:
        """Set the brightness in percentage.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
