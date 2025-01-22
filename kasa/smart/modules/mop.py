"""Implementation of vacuum mop."""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import Annotated

from ...feature import Feature
from ...module import FeatureAttribute
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)


class Waterlevel(IntEnum):
    """Water level for mopping."""

    Disable = 0
    Low = 1
    Medium = 2
    High = 3


class Mop(SmartModule):
    """Implementation of vacuum mop."""

    REQUIRED_COMPONENT = "mop"

    def _initialize_features(self) -> None:
        """Initialize features."""
        self._add_feature(
            Feature(
                self._device,
                id="mop_attached",
                name="Mop attached",
                container=self,
                icon="mdi:square-rounded",
                attribute_getter="mop_attached",
                category=Feature.Category.Info,
                type=Feature.BinarySensor,
            )
        )

        self._add_feature(
            Feature(
                self._device,
                id="mop_waterlevel",
                name="Mop water level",
                container=self,
                attribute_getter="waterlevel",
                attribute_setter="set_waterlevel",
                icon="mdi:water",
                choices_getter=lambda: list(Waterlevel.__members__),
                category=Feature.Category.Config,
                type=Feature.Type.Choice,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getMopState": {},
            "getCleanAttr": {"type": "global"},
        }

    @property
    def mop_attached(self) -> bool:
        """Return True if mop is attached."""
        return self.data["getMopState"]["mop_state"]

    @property
    def _settings(self) -> dict:
        """Return settings settings."""
        return self.data["getCleanAttr"]

    @property
    def waterlevel(self) -> Annotated[str, FeatureAttribute()]:
        """Return water level."""
        return Waterlevel(int(self._settings["cistern"])).name

    async def set_waterlevel(self, mode: str) -> Annotated[dict, FeatureAttribute()]:
        """Set waterlevel mode."""
        name_to_value = {x.name: x.value for x in Waterlevel}
        if mode not in name_to_value:
            raise ValueError("Invalid waterlevel %s, available %s", mode, name_to_value)

        settings = self._settings.copy()
        settings["cistern"] = name_to_value[mode]
        return await self.call("setCleanAttr", settings)
