"""Implementation of vacuum dustbin."""

from __future__ import annotations

import logging
from enum import IntEnum

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class Mode(IntEnum):
    """Dust collection modes."""

    Smart = 0
    Light = 1
    Balanced = 2
    Max = 3

    Unknown = -1000


class Dustbin(SmartModule):
    """Implementation of vacuum dustbin."""

    REQUIRED_COMPONENT = "dust_bucket"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="dustbin_empty",
                name="Empty dustbin",
                container=self,
                attribute_setter="start_emptying",
                category=Feature.Category.Primary,
                type=Feature.Action,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                id="dustbin_mode",
                name="Dustbin mode",
                container=self,
                attribute_getter="mode",
                attribute_setter="set_mode",
                icon="mdi:fan",
                choices_getter=lambda: list(Mode.__members__),
                category=Feature.Category.Config,
                type=Feature.Type.Choice,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getAutoDustCollection": {},
            "getDustCollectionInfo": {},
        }

    async def start_emptying(self) -> dict:
        """Start emptying the bin."""
        return await self.call(
            "setSwitchDustCollection",
            {
                "switch_dust_collection": True,
            },
        )

    @property
    def _auto_empty_settings(self) -> dict:
        """Return auto-empty settings."""
        return self.data["getDustCollectionInfo"]

    @property
    def mode(self) -> Mode:
        """Return auto-emptying mode."""
        return Mode(self._auto_empty_settings["dust_collection_mode"])

    async def set_mode(self, mode: Mode) -> dict:
        """Set auto-emptying mode."""
        settings = self._auto_empty_settings.copy()
        settings["dust_collection_mode"] = mode.value
        return await self.call("setDustCollectionInfo", settings)

    async def set_auto_emptying(self, on: bool) -> dict:
        """Toggle auto-emptying."""
        settings = self._auto_empty_settings.copy()
        settings["auto_dust_collection"] = on
        return await self.call("setDustCollectionInfo", settings)
