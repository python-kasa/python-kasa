"""Implementation of vacuum speaker."""

from __future__ import annotations

import logging
from typing import Annotated

from ...feature import Feature
from ...module import FeatureAttribute
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class Speaker(SmartModule):
    """Implementation of vacuum speaker."""

    REQUIRED_COMPONENT = "speaker"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="locate",
                name="Locate device",
                container=self,
                attribute_setter="locate",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                self._device,
                id="volume",
                name="Volume",
                container=self,
                attribute_getter="volume",
                attribute_setter="set_volume",
                range_getter=lambda: (0, 100),
                category=Feature.Category.Config,
                type=Feature.Type.Number,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getVolume": None,
        }

    @property
    def volume(self) -> Annotated[str, FeatureAttribute()]:
        """Return volume."""
        return self.data["volume"]

    async def set_volume(self, volume: int) -> Annotated[dict, FeatureAttribute()]:
        """Set volume."""
        if volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0 and 100")

        return await self.call("setVolume", {"volume": volume})

    async def locate(self) -> dict:
        """Play sound to locate the device."""
        return await self.call("playSelectAudio", {"audio_type": "seek_me"})
