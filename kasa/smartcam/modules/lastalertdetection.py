"""Module for the last alert reported by the camera."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartcammodule import SmartCamModule

if TYPE_CHECKING:
    from ...smart import SmartDevice

_LOGGER = logging.getLogger(__name__)


class LastAlertType(StrEnum):
    """Type of the alert reported by the camera."""

    Motion = "motion"
    Unknown = "unknown"


class LastAlertDetection(SmartCamModule):
    """Implementation of the last alert reported by the camera.

    Backed by ``getLastAlarmInfo`` (``last_alarm_time``/``last_alarm_type``),
    which is refreshed within a second of a detection and needs no SD card.
    The timestamp keeps advancing while the motion continues.

    Hub children are excluded as their modules are only refreshed once a day,
    which defeats the purpose of polling the last alert.
    """

    REQUIRED_COMPONENT = "detection"
    QUERY_GETTER_NAME = "getLastAlarmInfo"
    QUERY_MODULE_NAME = "system"
    QUERY_SECTION_NAMES = "last_alarm_info"

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._logged_unknown_types: set[str] = set()

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        return not self._device._is_hub_child

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
                id="last_alert_timestamp",
                name="Last alert time",
                attribute_getter="last_alert_timestamp",
                container=self,
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                id="last_alert_type",
                name="Last alert type",
                attribute_getter="last_alert_type",
                container=self,
                category=Feature.Category.Info,
                type=Feature.Type.Sensor,
            )
        )

    @property
    def last_alert_timestamp(self) -> datetime | None:
        """Return timestamp of the last alert, None if nothing was reported yet.

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
    def last_alert_type(self) -> LastAlertType | None:
        """Return the type of the last alert, None if nothing was reported yet.

        Unknown types are reported as :attr:`LastAlertType.Unknown`.
        """
        alert_type = self.data["last_alarm_info"].get("last_alarm_type")
        if not alert_type:
            return None
        try:
            return LastAlertType(alert_type)
        except ValueError:
            if alert_type not in self._logged_unknown_types:
                self._logged_unknown_types.add(alert_type)
                _LOGGER.warning(
                    "Unknown alert type, please create an issue describing it: %s",
                    alert_type,
                )
            return LastAlertType.Unknown
