"""Implementation of report module."""

from __future__ import annotations

from ...feature import Feature
from ..smartmodule import SmartModule


class ReportMode(SmartModule):
    """Implementation of report module."""

    REQUIRED_COMPONENT = "report_mode"
    QUERY_GETTER_NAME = "get_report_mode"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="report_interval",
                name="Report interval",
                container=self,
                attribute_getter="report_interval",
                unit_getter=lambda: "s",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def report_interval(self) -> int:
        """Reporting interval of a sensor device."""
        return self._device.sys_info["report_interval"]
