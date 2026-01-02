"""Module for floodlight controls."""

from __future__ import annotations
from typing import Annotated


from ...exceptions import KasaException
from ...feature import Feature
from ...iot.iotdevice import requires_update
from ...interfaces.light import LightState
from ...module import FeatureAttribute
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule


class Floodlight(SmartCamModule):
    """Implementation of floodlight controls."""

    REQUIRED_COMPONENT = "floodlight"

    _light_state: LightState

    def _initialize_features(self) -> None:
        """Initialize features."""
        device = self._device
        data = self.data
        config = data["getFloodlightConfig"]["floodlight"]["config"]
        status = data["getFloodlightStatus"]
        capability = data["getFloodlightCapability"]["floodlight"]["capability"]
        if (
            config is not None
            and status is not None
            and capability is not None
            and "intensity_level" in config
            and "intensity_level_max" in capability
            and "min_intensity" in capability
        ):
            self._add_feature(
                Feature(
                    device,
                    id="brightness",
                    name="Brightness",
                    container=self,
                    attribute_getter="brightness",
                    attribute_setter="set_brightness",
                    range_getter=lambda: (int(capability["min_intensity"]), int(capability["intensity_level_max"])),
                    type=Feature.Type.Number,
                    category=Feature.Category.Primary,
                )
            )
        if status is not None:
            self._add_feature(
                Feature(
                    self._device,
                    id="floodlight_state",
                    name="Floodlight state",
                    container=self,
                    attribute_getter="is_on",
                    attribute_setter="set_state",
                    type=Feature.Type.Switch,
                    category=Feature.Category.Primary,
                )
            )
        

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "getFloodlightConfig": {"floodlight": {"name": "config"}},
            "getFloodlightCapability": {"floodlight": {"name": "capability"}},
            "getFloodlightStatus": {"floodlight": {"get_floodlight_status": {}}}
        }

    @property
    def is_on(self) -> bool:
        """Return whether the device is on."""
        return int(self.data["getFloodlightStatus"]["status"]) == 1

    @allow_update_after
    async def set_state(self, on: bool) -> Annotated[dict, FeatureAttribute()]:
        """Set whether the floodlight is on.
        """
        params = {"floodlight": {"manual_floodlight_op": {"action": "start" if on else "stop"}}}
        return await self.call("manualFloodlightOp", params)

    @property
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness."""
        data = self.data
        if not self._device.modules["Floodlight"].has_feature("brightness"):  # pragma: no cover
            raise KasaException("Floodlight is not dimmable.")
        return int(data["getFloodlightConfig"]["floodlight"]["config"]["intensity_level"])

    @allow_update_after
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self._device.modules["Floodlight"].has_feature("brightness"):  # pragma: no cover
            raise KasaException("Floodlight is not dimmable.")

        params = {"floodlight": {"config": {"intensity_level": str(brightness)}}}
        return await self.call("setFloodlightConfig", params)
