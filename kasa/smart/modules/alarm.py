"""Implementation of alarm module."""

from __future__ import annotations

from typing import Literal

from ...feature import Feature
from ..smartmodule import SmartModule


class Alarm(SmartModule):
    """Implementation of alarm module."""

    REQUIRED_COMPONENT = "alarm"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "get_alarm_configure": None,
            "get_support_alarm_type_list": None,  # This should be needed only once
        }

    def _initialize_features(self) -> None:
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="alarm",
                name="Alarm",
                container=self,
                attribute_getter="active",
                icon="mdi:bell",
                type=Feature.Type.BinarySensor,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="alarm_source",
                name="Alarm source",
                container=self,
                attribute_getter="source",
                icon="mdi:bell",
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="alarm_sound",
                name="Alarm sound",
                container=self,
                attribute_getter="alarm_sound",
                attribute_setter="set_alarm_sound",
                category=Feature.Category.Config,
                type=Feature.Type.Choice,
                choices_getter="alarm_sounds",
            )
        )
        self._add_feature(
            Feature(
                device,
                id="alarm_volume",
                name="Alarm volume",
                container=self,
                attribute_getter="alarm_volume",
                attribute_setter="set_alarm_volume",
                category=Feature.Category.Config,
                type=Feature.Type.Choice,
                choices_getter=lambda: ["low", "normal", "high"],
            )
        )
        self._add_feature(
            Feature(
                device,
                id="alarm_duration",
                name="Alarm duration",
                container=self,
                attribute_getter="alarm_duration",
                attribute_setter="set_alarm_duration",
                category=Feature.Category.Config,
                type=Feature.Type.Number,
                range_getter=lambda: (1, 10 * 60),
            )
        )
        self._add_feature(
            Feature(
                device,
                id="test_alarm",
                name="Test alarm",
                container=self,
                attribute_setter="play",
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="stop_alarm",
                name="Stop alarm",
                container=self,
                attribute_setter="stop",
                type=Feature.Type.Action,
            )
        )

    @property
    def alarm_sound(self) -> str:
        """Return current alarm sound."""
        return self.data["get_alarm_configure"]["type"]

    async def set_alarm_sound(self, sound: str) -> dict:
        """Set alarm sound.

        See *alarm_sounds* for list of available sounds.
        """
        self._check_sound(sound)
        payload = self.data["get_alarm_configure"].copy()
        payload["type"] = sound
        return await self.call("set_alarm_configure", payload)

    @property
    def alarm_sounds(self) -> list[str]:
        """Return list of available alarm sounds."""
        return self.data["get_support_alarm_type_list"]["alarm_type_list"]

    @property
    def alarm_volume(self) -> Literal["low", "normal", "high"]:
        """Return alarm volume."""
        return self.data["get_alarm_configure"]["volume"]

    async def set_alarm_volume(self, volume: Literal["low", "normal", "high"]) -> dict:
        """Set alarm volume."""
        self._check_volume(volume)
        payload = self.data["get_alarm_configure"].copy()
        payload["volume"] = volume
        return await self.call("set_alarm_configure", payload)

    @property
    def alarm_duration(self) -> int:
        """Return alarm duration."""
        return self.data["get_alarm_configure"]["duration"]

    async def set_alarm_duration(self, duration: int) -> dict:
        """Set alarm duration."""
        self._check_duration(duration)
        payload = self.data["get_alarm_configure"].copy()
        payload["duration"] = duration
        return await self.call("set_alarm_configure", payload)

    @property
    def active(self) -> bool:
        """Return true if alarm is active."""
        return self._device.sys_info["in_alarm"]

    @property
    def source(self) -> str | None:
        """Return the alarm cause."""
        src = self._device.sys_info["in_alarm_source"]
        return src if src else None

    async def play(
        self,
        *,
        duration: int | None = None,
        volume: Literal["low", "normal", "high"] | None = None,
        sound: str | None = None,
    ) -> dict:
        """Play alarm.

        The optional *duration*, *volume*, and *sound* to override the device settings.
        *volume* can be set to 'low', 'normal', or 'high'.
        *duration* is in seconds.
        See *alarm_sounds* for the list of sounds available for the device.
        """
        params: dict[str, str | int] = {}

        if duration is not None:
            self._check_duration(duration)
            params["alarm_duration"] = duration

        if volume is not None:
            self._check_volume(volume)
            params["alarm_volume"] = volume

        if sound is not None:
            self._check_sound(sound)
            params["alarm_type"] = sound

        return await self.call("play_alarm", params)

    async def stop(self) -> dict:
        """Stop alarm."""
        return await self.call("stop_alarm")

    def _check_volume(self, volume: str) -> None:
        """Raise an exception on invalid volume."""
        if volume not in ["low", "normal", "high"]:
            raise ValueError(f"Invalid volume {volume} available: low, normal, high")

    def _check_duration(self, duration: int) -> None:
        """Raise an exception on invalid duration."""
        if duration < 1 or duration > 10 * 60:
            raise ValueError(f"Invalid duration {duration} available: 1-600")

    def _check_sound(self, sound: str) -> None:
        """Raise an exception on invalid sound."""
        if sound not in self.alarm_sounds:
            raise ValueError(f"Invalid sound {sound} available: {self.alarm_sounds}")
