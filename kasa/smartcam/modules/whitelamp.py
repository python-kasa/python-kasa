"""Module for white lamp (floodlight) controls on Tapo outdoor cameras."""

from __future__ import annotations

import logging
from typing import Annotated

from ...feature import Feature
from ...module import FeatureAttribute
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class WhiteLamp(SmartCamModule):
    """Implementation of white lamp controls for outdoor cameras (e.g. C325WB).

    The white lamp is the built-in floodlight that can be triggered manually
    or by motion events. It is distinct from the LED status indicator.
    """

    REQUIRED_COMPONENT = "whiteLamp"

    QUERY_GETTER_NAME = "getWhitelampStatus"
    QUERY_MODULE_NAME = "image"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        q["getWhitelampStatus"] = {self.QUERY_MODULE_NAME: {"get_wtl_status": ["null"]}}
        q["getWhitelampConfig"] = {self.QUERY_MODULE_NAME: {"name": "switch"}}
        return q

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="white_lamp_state",
                name="White lamp state",
                container=self,
                attribute_getter="is_on",
                attribute_setter="set_state",
                type=Feature.Type.Switch,
                category=Feature.Category.Primary,
            )
        )
        config = self.data["getWhitelampConfig"]["image"]["switch"]
        if "wtl_intensity_level" in config:
            self._add_feature(
                Feature(
                    self._device,
                    id="white_lamp_brightness",
                    name="White lamp brightness",
                    container=self,
                    attribute_getter="brightness",
                    attribute_setter="set_brightness",
                    range_getter=lambda: (1, 100),
                    type=Feature.Type.Number,
                    category=Feature.Category.Config,
                )
            )

    @property
    def is_on(self) -> bool:
        """Return whether the white lamp is on."""
        return int(self.data["getWhitelampStatus"]["status"]) == 1

    @allow_update_after
    async def set_state(self, on: bool) -> Annotated[dict, FeatureAttribute()]:
        """Turn the white lamp on or off."""
        if self.is_on != on:
            return await self.call(
                "reverseWhitelampStatus", {"image": {"reverse_wtl_status": ["null"]}}
            )
        return {}

    @property
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness (1-100)."""
        return int(
            self.data["getWhitelampConfig"]["image"]["switch"]["wtl_intensity_level"]
        )

    @allow_update_after
    async def set_brightness(
        self, brightness: int
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the white lamp brightness (1-100)."""
        return await self._device._query_setter_helper(
            "setWhitelampConfig",
            self.QUERY_MODULE_NAME,
            "switch",
            {"wtl_intensity_level": str(brightness)},
        )
