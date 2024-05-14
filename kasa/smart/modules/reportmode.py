"""Implementation of report module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class ReportMode(SmartModule):
    """Implementation of report module."""

    REQUIRED_COMPONENT = "report_mode"
    QUERY_GETTER_NAME = "get_report_mode"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                id="report_interval",
                name="Report interval",
                container=self,
                attribute_getter="report_interval",
                category=Feature.Category.Debug,
            )
        )

    @property
    def report_interval(self):
        """Reporting interval of a sensor device."""
        return self._device.sys_info["report_interval"]
