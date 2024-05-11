"""Implementation of alarm module."""

from __future__ import annotations

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

    def _initialize_features(self):
        """Initialize features.

        This is implemented as some features depend on device responses.
        """
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
                choices=["low", "normal", "high"],
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
    def alarm_sound(self):
        """Return current alarm sound."""
        return self.data["get_alarm_configure"]["type"]

    async def set_alarm_sound(self, sound: str):
        """Set alarm sound.

        See *alarm_sounds* for list of available sounds.
        """
        payload = self.data["get_alarm_configure"].copy()
        payload["type"] = sound
        return await self.call("set_alarm_configure", payload)

    @property
    def alarm_sounds(self) -> list[str]:
        """Return list of available alarm sounds."""
        return self.data["get_support_alarm_type_list"]["alarm_type_list"]

    @property
    def alarm_volume(self):
        """Return alarm volume."""
        return self.data["get_alarm_configure"]["volume"]

    async def set_alarm_volume(self, volume: str):
        """Set alarm volume."""
        payload = self.data["get_alarm_configure"].copy()
        payload["volume"] = volume
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

    async def play(self):
        """Play alarm."""
        return await self.call("play_alarm")

    async def stop(self):
        """Stop alarm."""
        return await self.call("stop_alarm")
