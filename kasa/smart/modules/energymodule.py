"""Implementation of energy monitoring module."""
from typing import TYPE_CHECKING, Dict, Optional

from ...emeterstatus import EmeterStatus
from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class EnergyModule(SmartModule):
    """Implementation of energy monitoring module."""

    REQUIRED_COMPONENT = "energy_monitoring"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                name="Current consumption",
                attribute_getter="current_power",
                container=self,
            )
        )  # W or mW?
        self._add_feature(
            Feature(
                device,
                name="Today's consumption",
                attribute_getter="emeter_today",
                container=self,
            )
        )  # Wh or kWh?
        self._add_feature(
            Feature(
                device,
                name="This month's consumption",
                attribute_getter="emeter_this_month",
                container=self,
            )
        )  # Wh or kWH?

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {
            "get_energy_usage": None,
            # The current_power in get_energy_usage is more precise (mw vs. w),
            # making this rather useless, but maybe there are version differences?
            "get_current_power": None,
        }

    @property
    def current_power(self):
        """Current power."""
        return self.emeter_realtime.power

    @property
    def energy(self):
        """Return get_energy_usage results."""
        return self.data["get_energy_usage"]

    @property
    def emeter_realtime(self):
        """Get the emeter status."""
        # TODO: Perhaps we should get rid of emeterstatus altogether for smartdevices
        return EmeterStatus(
            {
                "power_mw": self.energy.get("current_power"),
                "total": self._convert_energy_data(
                    self.energy.get("today_energy"), 1 / 1000
                ),
            }
        )

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""
        return self._convert_energy_data(self.energy.get("month_energy"), 1 / 1000)

    @property
    def emeter_today(self) -> Optional[float]:
        """Get the emeter value for today."""
        return self._convert_energy_data(self.energy.get("today_energy"), 1 / 1000)

    def _convert_energy_data(self, data, scale) -> Optional[float]:
        """Return adjusted emeter information."""
        return data if not data else data * scale
