"""Implementation of vacuum speaker."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


class VacuumSpeaker(SmartModule):
    """Implementation of vacuum speaker."""

    REQUIRED_COMPONENT = "speaker"

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="vacuum_locate",
                name="Locate vacuum",
                container=self,
                attribute_setter="locate",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="vacuum_volume",
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
    def volume(self) -> str:
        """Return volume."""
        return self.data["volume"]

    async def set_volume(self, volume: int) -> dict:
        """Set volume."""
        if volume < 0 or volume > 100:
            raise ValueError("Volume must be between 0 and 100")

        return await self.call("setVolume", {"volume": volume})

    async def locate(self) -> dict:
        """Play sound to locate the device."""
        return await self.call("playSelectAudio", {"audio_type": "seek_me"})
