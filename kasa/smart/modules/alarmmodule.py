"""Implementation of alarm module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class AlarmModule(SmartModule):
    """Implementation of alarm module."""

    REQUIRED_COMPONENT = "alarm"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {
            "get_alarm_configure": None,
            "get_support_alarm_type_list": None,  # This should be needed only once
        }

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Alarm",
                container=self,
                attribute_getter="active",
                icon="mdi:bell",
                type=Feature.Type.BinarySensor,
            )
        )
        self._add_feature(
            Feature(
                device,
                "Alarm source",
                container=self,
                attribute_getter="source",
                icon="mdi:bell",
            )
        )
        self._add_feature(
            Feature(
                device, "Alarm sound", container=self, attribute_getter="alarm_sound"
            )
        )
        self._add_feature(
            Feature(
                device, "Alarm volume", container=self, attribute_getter="alarm_volume"
            )
        )
        self._add_feature(
            Feature(
                device,
                "Test alarm",
                container=self,
                attribute_setter="play",
                type=Feature.Type.Action,
            )
        )
        self._add_feature(
            Feature(
                device,
                "Stop alarm",
                container=self,
                attribute_setter="stop",
                type=Feature.Type.Action,
            )
        )

    @property
    def alarm_sound(self):
        """Return current alarm sound."""
        return self.data["get_alarm_configure"]["type"]

    @property
    def alarm_sounds(self) -> list[str]:
        """Return list of available alarm sounds."""
        return self.data["get_support_alarm_type_list"]["alarm_type_list"]

    @property
    def alarm_volume(self):
        """Return alarm volume."""
        return self.data["get_alarm_configure"]["volume"]

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
