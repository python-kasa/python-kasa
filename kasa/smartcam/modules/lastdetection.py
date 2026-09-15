"""Module for the last detection reported by the camera."""

from __future__ import annotations

from datetime import datetime

from ...feature import Feature
from ..smartcammodule import SmartCamModule


class LastDetection(SmartCamModule):
    """Implementation of the last detection reported by the camera.

    Backed by ``getLastAlarmInfo`` (``last_alarm_time``/``last_alarm_type``),
    which is refreshed within a second of a detection and needs no SD card.
    The timestamp keeps advancing while the motion continues.

    Hub children are excluded as their modules are only refreshed once a day,
    which defeats the purpose of polling the last detection.
    """

    REQUIRED_COMPONENT = "detection"
    QUERY_GETTER_NAME = "getLastAlarmInfo"
    QUERY_MODULE_NAME = "system"
    QUERY_SECTION_NAMES = "last_alarm_info"

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return not self._device._is_hub_child

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="last_detection_timestamp",
                name="Last detection time",
                attribute_getter="last_detection_timestamp",
                container=self,
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                id="last_detection_type",
                name="Last detection type",
                attribute_getter="last_detection_type",
                container=self,
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )

    @property
    def last_detection_timestamp(self) -> datetime | None:
        """Return timestamp of the last detection, None if nothing was detected yet.

        Devices report an empty string or 0 when nothing has been detected yet.
        Unparseable values are reported as None as well.
        """
        try:
            timestamp = int(self.data["last_alarm_info"].get("last_alarm_time"))
            if not timestamp:
                return None
            return datetime.fromtimestamp(timestamp, tz=self._device.timezone)
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    @property
    def last_detection_type(self) -> str | None:
        """Return the type of the last detection, e.g. motion."""
        return self.data["last_alarm_info"].get("last_alarm_type") or None
