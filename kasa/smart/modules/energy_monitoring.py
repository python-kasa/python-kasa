from typing import Dict

from ..smartmodule import SmartModule


class EnergyMonitoring(SmartModule):
    REQUIRED_COMPONENT = "energy_monitoring"

    def query(self) -> Dict:
        return {
            "get_energy_usage": None,
            "get_current_power": None,
        }
