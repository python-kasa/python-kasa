"""Implementation of alarm module."""

from __future__ import annotations

from typing import Literal

from ...feature import Feature
from ..smartcameramodule import SmartCameraModule

DURATION_MIN = 0
DURATION_MAX = 6000

VOLUME_MIN = 1
VOLUME_MAX = 10


class Alarm(SmartCameraModule):
    """Implementation of alarm module."""

    # Needs a different name to avoid clashing with SmartAlarm
    NAME = "SmartCameraAlarm"

    REQUIRED_COMPONENT = "siren"
    QUERY_GETTER_NAME = "getSirenStatus"
    QUERY_MODULE_NAME = "siren"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        q["getSirenConfig"] = {self.QUERY_MODULE_NAME: {}}
        q["getSirenTypeList"] = {self.QUERY_MODULE_NAME: {}}

        return q

    def _initialize_features(self) -> None:
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
                type=Feature.Type.Number,
                range_getter=lambda: (VOLUME_MIN, VOLUME_MAX),
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
                range_getter=lambda: (DURATION_MIN, DURATION_MAX),
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
        return self.data["getSirenConfig"]["siren_type"]

    async def set_alarm_sound(self, sound: str) -> dict:
        """Set alarm sound.

        See *alarm_sounds* for list of available sounds.
        """
        if sound not in self.alarm_sounds:
            msg = f"sound must be one of {', '.join(self.alarm_sounds)}: {sound}"
            raise ValueError(msg)
        return await self.call("setSirenConfig", {"siren": {"siren_type": sound}})

    @property
    def alarm_sounds(self) -> list[str]:
        """Return list of available alarm sounds."""
        return self.data["getSirenTypeList"]["siren_type_list"]

    @property
    def alarm_volume(self) -> Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
        """Return alarm volume."""
        return int(self.data["getSirenConfig"]["volume"])  # type: ignore[return-value]

    async def set_alarm_volume(
        self, volume: Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ) -> dict:
        """Set alarm volume."""
        return await self.call("setSirenConfig", {"siren": {"volume": str(volume)}})

    @property
    def alarm_duration(self) -> int:
        """Return alarm duration."""
        return self.data["getSirenConfig"]["duration"]

    async def set_alarm_duration(self, duration: int) -> dict:
        """Set alarm volume."""
        return await self.call("setSirenConfig", {"siren": {"duration": duration}})

    @property
    def active(self) -> bool:
        """Return true if alarm is active."""
        return self.data["getSirenStatus"]["status"] != "off"

    @property
    def source(self) -> str | None:
        """Return the alarm cause."""
        return None

    async def play(self) -> dict:
        """Play alarm."""
        return await self.call("setSirenStatus", {"siren": {"status": "on"}})

    async def stop(self) -> dict:
        """Stop alarm."""
        return await self.call("setSirenStatus", {"siren": {"status": "off"}})
