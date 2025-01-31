"""Implementation of the dimmer config module found in dimmers."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Final, cast

from ...exceptions import KasaException
from ...feature import Feature
from ..iotmodule import IotModule, merge

_LOGGER = logging.getLogger(__name__)


def _td_to_ms(td: timedelta) -> int:
    """
    Convert timedelta to integer milliseconds.

    Uses default float to integer rounding.
    """
    return int(td / timedelta(milliseconds=1))


class Dimmer(IotModule):
    """Implements the dimmer config module."""

    THRESHOLD_ABS_MIN: Final[int] = 0
    # Strange value, but verified against hardware (KS220).
    THRESHOLD_ABS_MAX: Final[int] = 51
    FADE_TIME_ABS_MIN: Final[timedelta] = timedelta(seconds=0)
    # Arbitrary, but set low intending GENTLE FADE for longer fades.
    FADE_TIME_ABS_MAX: Final[timedelta] = timedelta(seconds=10)
    GENTLE_TIME_ABS_MIN: Final[timedelta] = timedelta(seconds=0)
    # Arbitrary, but reasonable default.
    GENTLE_TIME_ABS_MAX: Final[timedelta] = timedelta(seconds=120)
    # Verified against KS220.
    RAMP_RATE_ABS_MIN: Final[int] = 10
    # Verified against KS220.
    RAMP_RATE_ABS_MAX: Final[int] = 50

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_threshold_min",
                name="Minimum dimming level",
                icon="mdi:lightbulb-on-20",
                attribute_getter="threshold_min",
                attribute_setter="set_threshold_min",
                range_getter=lambda: (self.THRESHOLD_ABS_MIN, self.THRESHOLD_ABS_MAX),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_fade_off_time",
                name="Dimmer fade off time",
                icon="mdi:clock-in",
                attribute_getter="fade_off_time",
                attribute_setter="set_fade_off_time",
                range_getter=lambda: (
                    _td_to_ms(self.FADE_TIME_ABS_MIN),
                    _td_to_ms(self.FADE_TIME_ABS_MAX),
                ),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_fade_on_time",
                name="Dimmer fade on time",
                icon="mdi:clock-out",
                attribute_getter="fade_on_time",
                attribute_setter="set_fade_on_time",
                range_getter=lambda: (
                    _td_to_ms(self.FADE_TIME_ABS_MIN),
                    _td_to_ms(self.FADE_TIME_ABS_MAX),
                ),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_gentle_off_time",
                name="Dimmer gentle off time",
                icon="mdi:clock-in",
                attribute_getter="gentle_off_time",
                attribute_setter="set_gentle_off_time",
                range_getter=lambda: (
                    _td_to_ms(self.GENTLE_TIME_ABS_MIN),
                    _td_to_ms(self.GENTLE_TIME_ABS_MAX),
                ),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_gentle_on_time",
                name="Dimmer gentle on time",
                icon="mdi:clock-out",
                attribute_getter="gentle_on_time",
                attribute_setter="set_gentle_on_time",
                range_getter=lambda: (
                    _td_to_ms(self.GENTLE_TIME_ABS_MIN),
                    _td_to_ms(self.GENTLE_TIME_ABS_MAX),
                ),
                type=Feature.Type.Number,
                category=Feature.Category.Config,
            )
        )

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="dimmer_ramp_rate",
                name="Dimmer ramp rate",
                icon="mdi:clock-fast",
                attribute_getter="ramp_rate",
                attribute_setter="set_ramp_rate",
                range_getter=lambda: (self.RAMP_RATE_ABS_MIN, self.RAMP_RATE_ABS_MAX),
                type=Feature.Type.Number,
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
    def config(self) -> dict[str, Any]:
        """Return current configuration."""
        return self.data["get_dimmer_parameters"]

    @property
    def threshold_min(self) -> int:
        """Return the minimum dimming level for this dimmer."""
        return self.config["minThreshold"]

    async def set_threshold_min(self, min: int) -> dict:
        """Set the minimum dimming level for this dimmer.

        The value will depend on the luminaries connected to the dimmer.

        :param min: The minimum dimming level, in the range 0-51.
        """
        if min < self.THRESHOLD_ABS_MIN or min > self.THRESHOLD_ABS_MAX:
            raise KasaException(
                "Minimum dimming threshold is outside the supported range: "
                f"{self.THRESHOLD_ABS_MIN}-{self.THRESHOLD_ABS_MAX}"
            )
        return await self.call("calibrate_brightness", {"minThreshold": min})

    @property
    def fade_off_time(self) -> timedelta:
        """Return the fade off animation duration."""
        return timedelta(milliseconds=cast(int, self.config["fadeOffTime"]))

    async def set_fade_off_time(self, time: int | timedelta) -> dict:
        """Set the duration of the fade off animation.

        :param time: The animation duration, in ms.
        """
        if isinstance(time, int):
            time = timedelta(milliseconds=time)
        if time < self.FADE_TIME_ABS_MIN or time > self.FADE_TIME_ABS_MAX:
            raise KasaException(
                "Fade time is outside the bounds of the supported range:"
                f"{self.FADE_TIME_ABS_MIN}-{self.FADE_TIME_ABS_MAX}"
            )
        return await self.call("set_fade_off_time", {"fadeTime": _td_to_ms(time)})

    @property
    def fade_on_time(self) -> timedelta:
        """Return the fade on animation duration."""
        return timedelta(milliseconds=cast(int, self.config["fadeOnTime"]))

    async def set_fade_on_time(self, time: int | timedelta) -> dict:
        """Set the duration of the fade on animation.

        :param time: The animation duration, in ms.
        """
        if isinstance(time, int):
            time = timedelta(milliseconds=time)
        if time < self.FADE_TIME_ABS_MIN or time > self.FADE_TIME_ABS_MAX:
            raise KasaException(
                "Fade time is outside the bounds of the supported range:"
                f"{self.FADE_TIME_ABS_MIN}-{self.FADE_TIME_ABS_MAX}"
            )
        return await self.call("set_fade_on_time", {"fadeTime": _td_to_ms(time)})

    @property
    def gentle_off_time(self) -> timedelta:
        """Return the gentle fade off animation duration."""
        return timedelta(milliseconds=cast(int, self.config["gentleOffTime"]))

    async def set_gentle_off_time(self, time: int | timedelta) -> dict:
        """Set the duration of the gentle fade off animation.

        :param time: The animation duration, in ms.
        """
        if isinstance(time, int):
            time = timedelta(milliseconds=time)
        if time < self.GENTLE_TIME_ABS_MIN or time > self.GENTLE_TIME_ABS_MAX:
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range: "
                f"{self.GENTLE_TIME_ABS_MIN}-{self.GENTLE_TIME_ABS_MAX}."
            )
        return await self.call("set_gentle_off_time", {"duration": _td_to_ms(time)})

    @property
    def gentle_on_time(self) -> timedelta:
        """Return the gentle fade on animation duration."""
        return timedelta(milliseconds=cast(int, self.config["gentleOnTime"]))

    async def set_gentle_on_time(self, time: int | timedelta) -> dict:
        """Set the duration of the gentle fade on animation.

        :param time: The animation duration, in ms.
        """
        if isinstance(time, int):
            time = timedelta(milliseconds=time)
        if time < self.GENTLE_TIME_ABS_MIN or time > self.GENTLE_TIME_ABS_MAX:
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range: "
                f"{self.GENTLE_TIME_ABS_MIN}-{self.GENTLE_TIME_ABS_MAX}."
            )
        return await self.call("set_gentle_on_time", {"duration": _td_to_ms(time)})

    @property
    def ramp_rate(self) -> int:
        """Return the rate that the dimmer buttons increment the dimmer level."""
        return self.config["rampRate"]

    async def set_ramp_rate(self, rate: int) -> dict:
        """Set how quickly to ramp the dimming level when using the dimmer buttons.

        :param rate: The rate to increment the dimming level with each press.
        """
        if rate < self.RAMP_RATE_ABS_MIN or rate > self.RAMP_RATE_ABS_MAX:
            raise KasaException(
                "Gentle off time is outside the bounds of the supported range:"
                f"{self.RAMP_RATE_ABS_MIN}-{self.RAMP_RATE_ABS_MAX}"
            )
        return await self.call("set_button_ramp_rate", {"rampRate": rate})
