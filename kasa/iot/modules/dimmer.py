"""Implementation of the dimmer config module found in dimmers."""

from __future__ import annotations

import logging

from ...exceptions import KasaException
from ...feature import Feature
from ..iotmodule import IotModule, merge

_LOGGER = logging.getLogger(__name__)


class Dimmer(IotModule):
    """Implements the dimmer config module."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Only add features if the device supports the module
        if "get_dimmer_parameters" not in self.data:
            return

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_threshold_min",
                name="Minimum Dimming Level",
                icon="mdi:lightbulb-on-20",
                attribute_getter="threshold_min",
                attribute_setter="set_threshold_min",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_fade_off_time",
                name="Dimmer Fade Off Time",
                icon="mdi:clock-in",
                attribute_getter="fade_off_time",
                attribute_setter="set_fade_off_time",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_fade_on_time",
                name="Dimmer Fade On Time",
                icon="mdi:clock-out",
                attribute_getter="fade_on_time",
                attribute_setter="set_fade_on_time",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_gentle_off_time",
                name="Dimmer Gentle Off Time",
                icon="mdi:clock-in",
                attribute_getter="gentle_off_time",
                attribute_setter="set_gentle_off_time",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_gentle_on_time",
                name="Dimmer Gentle On Time",
                icon="mdi:clock-out",
                attribute_getter="gentle_on_time",
                attribute_setter="set_gentle_on_time",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_ramp_rate",
                name="Dimmer Ramp Rate",
                icon="mdi:clock-fast",
                attribute_getter="ramp_rate",
                attribute_setter="set_ramp_rate",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )

    def query(self) -> dict:
        """Request Dimming configuration."""
        req = merge(
            self.query_for_command("get_dimmer_parameters"),
            self.query_for_command("get_default_behavior"),
        )

        return req

    @property
    def config(self) -> dict:
        """Return current configuration."""
        return self.data["get_dimmer_parameters"]

    @property
    def threshold_min(self) -> int | None:
        """Return the minimum dimming level for this dimmer."""
        if (min := self.config.get("minThreshold")) is not None:
            return int(min)
        return None

    async def set_threshold_min(self, min: int) -> dict:
        """
        Set the minimum dimming level for this dimmer.

        The value will depend on the luminaries connected to the dimmer.

        :param min: The minimum dimming level, in the range 0-51.
        """
        if (min < 0) or (min > 51):
            raise KasaException(
                "Minimum dimming threshold is outside the supported range: 0-51."
            )
        return await self.call("calibrate_brightness", {"minThreshold": min})

    @property
    def fade_off_time(self) -> int | None:
        """Return the fade off animation duration."""
        if (fade_time := self.config.get("fadeOffTime")) is not None:
            return int(fade_time)
        return None

    async def set_fade_off_time(self, time: int) -> dict:
        """
        Set the duration of the fade off animation.

        :param time: The animation duration, in ms.
        """
        if (time < 0) or (time > 10_000):
            # FYI:  Not sure if there is really a max bound here,
            #       but anything above 10s seems ridiculous.
            raise KasaException(
                "Fade time is outside the bounds of the supported range: 0-10,000."
            )
        return await self.call("set_fade_on_time", {"fadeTime": time})

    @property
    def fade_on_time(self) -> int | None:
        """Return the fade on animation duration."""
        if (fade_time := self.config.get("fadeOnTime")) is not None:
            return int(fade_time)
        return None

    async def set_fade_on_time(self, time: int) -> dict:
        """
        Set the duration of the fade on animation.

        :param time: The animation duration, in ms.
        """
        if (time < 0) or (time > 10_000):
            # FYI:  Not sure if there is really a max bound here,
            #       but anything above 10s seems ridiculous.
            raise KasaException(
                "Fade time is outside the bounds of the supported range: 0-10,000."
            )
        return await self.call("set_fade_on_time", {"fadeTime": time})

    @property
    def gentle_off_time(self) -> int | None:
        """Return the gentle fade off animation duration."""
        if (duration := self.config.get("gentleOffTime")) is not None:
            return int(duration)
        return None

    async def set_gentle_off_time(self, time: int) -> dict:
        """
        Set the duration of the gentle fade off animation.

        :param time: The animation duration, in ms.
        """
        if (time < 0) or (time > 100_000):
            # FYI:  Not sure if there is really a max bound here,
            #       but anything above 100s seems ridiculous.
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range: "
                "0-100,000."
            )
        return await self.call("set_gentle_off_time", {"duration": time})

    @property
    def gentle_on_time(self) -> int | None:
        """Return the gentle fade on animation duration."""
        if (duration := self.config.get("gentleOnTime")) is not None:
            return int(duration)
        return None

    async def set_gentle_on_time(self, time: int) -> dict:
        """
        Set the duration of the gentle fade on animation.

        :param time: The animation duration, in ms.
        """
        if (time < 0) or (time > 100_000):
            # FYI:  Not sure if there is really a max bound here,
            #       but anything above 100s seems ridiculous.
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range: "
                "0-100,000."
            )
        return await self.call("set_gentle_on_time", {"duration": time})

    @property
    def ramp_rate(self) -> int | None:
        """Return the rate that the dimmer buttons increment the dimmer level."""
        if (rate := self.config.get("rampRate")) is not None:
            return int(rate)
        return None

    async def set_ramp_rate(self, rate: int) -> dict:
        """
        Set how quickly to ramp the dimming level when using the dimmer buttons.

        :param rate: The rate to increment the dimming level with each press.
        """
        if (rate < 10) or (rate > 50):
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range: 10-50"
            )
        return await self.call("set_button_ramp_rate", {"rampRate": rate})
