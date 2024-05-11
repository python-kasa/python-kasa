"""Implementation of energy monitoring module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...emeterstatus import EmeterStatus
from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class Energy(SmartModule):
    """Implementation of energy monitoring module."""

    REQUIRED_COMPONENT = "energy_monitoring"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "consumption_current",
                name="Current consumption",
                attribute_getter="current_power",
                container=self,
                unit="W",
                precision_hint=1,
                category=Feature.Category.Primary,
            )
        )
        self._add_feature(
            Feature(
                device,
                "consumption_today",
                name="Today's consumption",
                attribute_getter="emeter_today",
                container=self,
                unit="Wh",
                precision_hint=2,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                "consumption_this_month",
                name="This month's consumption",
                attribute_getter="emeter_this_month",
                container=self,
                unit="Wh",
                precision_hint=2,
                category=Feature.Category.Info,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req = {
            "get_energy_usage": None,
        }
        if self.supported_version > 1:
            req["get_current_power"] = None
        return req

    @property
    def current_power(self) -> float | None:
        """Current power in watts."""
        if power := self.energy.get("current_power"):
            return power / 1_000
        return None

    @property
    def energy(self):
        """Return get_energy_usage results."""
        if en := self.data.get("get_energy_usage"):
            return en
        return self.data

    @property
    def emeter_realtime(self):
        """Get the emeter status."""
        # TODO: Perhaps we should get rid of emeterstatus altogether for smartdevices
        return EmeterStatus(
            {
                "power_mw": self.energy.get("current_power"),
                "total": self.energy.get("today_energy") / 1_000,
            }
        )

    @property
    def emeter_this_month(self) -> float | None:
        """Get the emeter value for this month."""
        return self.energy.get("month_energy")

    @property
    def emeter_today(self) -> float | None:
        """Get the emeter value for today."""
        return self.energy.get("today_energy")
