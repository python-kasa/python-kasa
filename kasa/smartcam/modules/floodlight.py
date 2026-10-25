"""Module for floodlight controls ("whitelamp" module) on Tapo outdoor cameras."""

from __future__ import annotations

from typing import Annotated

from ...exceptions import KasaException
from ...feature import Feature
from ...interfaces.light import HSV, LightState
from ...interfaces.light import Light as LightInterface
from ...module import FeatureAttribute
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule


class FloodLight(SmartCamModule, LightInterface):
    """Implementation of floodlight controls for outdoor cameras."""

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
                id="floodlight",
                name="Floodlight",
                container=self,
                attribute_getter="is_on",
                attribute_setter="set_on",
                type=Feature.Type.Switch,
                category=Feature.Category.Primary,
            )
        )
        if self._is_dimmable:
            self._add_feature(
                Feature(
                    self._device,
                    id="floodlight_brightness",
                    name="Floodlight brightness",
                    container=self,
                    attribute_getter="brightness",
                    attribute_setter="set_brightness",
                    range_getter=lambda: (1, 100),
                    type=Feature.Type.Number,
                    category=Feature.Category.Config,
                )
            )

    @property
    def _config(self) -> dict:
        return self.data["getWhitelampConfig"]["image"]["switch"]

    @property
    def _is_dimmable(self) -> bool:
        return "wtl_intensity_level" in self._config

    @property
    def is_on(self) -> bool:
        """Return whether the floodlight is on."""
        return int(self.data["getWhitelampStatus"]["status"]) == 1

    @allow_update_after
    async def set_on(self, on: bool) -> dict:
        """Turn the floodlight on or off."""
        if self.is_on != on:
            return await self.call(
                "reverseWhitelampStatus", {"image": {"reverse_wtl_status": ["null"]}}
            )
        return {}

    @property
    def brightness(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current brightness in percentage."""
        if not self._is_dimmable:
            raise KasaException("Floodlight is not dimmable.")

        return int(self._config["wtl_intensity_level"])

    @allow_update_after
    async def set_brightness(
        self, brightness: int, *, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the brightness in percentage.

        Note, transition is not supported and will be ignored.

        :param int brightness: brightness in percent
        :param int transition: transition in milliseconds.
        """
        if not self._is_dimmable:
            raise KasaException("Floodlight is not dimmable.")

        return await self._device._query_setter_helper(
            "setWhitelampConfig",
            self.QUERY_MODULE_NAME,
            "switch",
            {"wtl_intensity_level": str(brightness)},
        )

    @property
    def hsv(self) -> Annotated[HSV, FeatureAttribute()]:
        """Return the current HSV state of the light."""
        raise KasaException("Floodlight does not support color.")

    @property
    def color_temp(self) -> Annotated[int, FeatureAttribute()]:
        """Return the current color temperature."""
        raise KasaException("Floodlight does not support colortemp.")

    async def set_hsv(
        self,
        hue: int,
        saturation: int,
        value: int | None = None,
        *,
        transition: int | None = None,
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set new HSV."""
        raise KasaException("Floodlight does not support color.")

    async def set_color_temp(
        self, temp: int, *, brightness: int | None = None, transition: int | None = None
    ) -> Annotated[dict, FeatureAttribute()]:
        """Set the color temperature."""
        raise KasaException("Floodlight does not support colortemp.")

    @property
    def state(self) -> LightState:
        """Return the current light state."""
        state = LightState(light_on=self.is_on)
        if self._is_dimmable:
            state.brightness = self.brightness
        return state

    async def set_state(self, state: LightState) -> dict:
        """Set the light state."""
        # brightness of 0 turns off the light, it's not a valid brightness
        if state.brightness == 0:
            return await self.set_on(False)

        res: dict = {}
        if state.brightness is not None:
            res.update(await self.set_brightness(state.brightness))
        light_on = state.light_on
        if light_on is None and state.brightness is not None:
            light_on = True
        if light_on is not None:
            res.update(await self.set_on(light_on))
        return res
