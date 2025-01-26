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

    Off = -1_000


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
                category=Feature.Category.Config,
                type=Feature.Action,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                id="dustbin_autocollection_enabled",
                name="Automatic emptying enabled",
                container=self,
                attribute_getter="auto_collection",
                attribute_setter="set_auto_collection",
                category=Feature.Category.Config,
                type=Feature.Switch,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                id="dustbin_mode",
                name="Automatic emptying mode",
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
    def _settings(self) -> dict:
        """Return auto-empty settings."""
        return self.data["getDustCollectionInfo"]

    @property
    def mode(self) -> str:
        """Return auto-emptying mode."""
        if self.auto_collection is False:
            return Mode.Off.name
        return Mode(self._settings["dust_collection_mode"]).name

    async def set_mode(self, mode: str) -> dict:
        """Set auto-emptying mode."""
        name_to_value = {x.name: x.value for x in Mode}
        if mode not in name_to_value:
            raise ValueError(
                "Invalid auto/emptying mode speed %s, available %s", mode, name_to_value
            )

        if mode == Mode.Off.name:
            return await self.set_auto_collection(False)

        # Make a copy just in case, even when we are overriding both settings
        settings = self._settings.copy()
        settings["auto_dust_collection"] = True
        settings["dust_collection_mode"] = name_to_value[mode]

        return await self.call("setDustCollectionInfo", settings)

    @property
    def auto_collection(self) -> dict:
        """Return auto-emptying config."""
        return self._settings["auto_dust_collection"]

    async def set_auto_collection(self, on: bool) -> dict:
        """Toggle auto-emptying."""
        settings = self._settings.copy()
        settings["auto_dust_collection"] = on
        return await self.call("setDustCollectionInfo", settings)
