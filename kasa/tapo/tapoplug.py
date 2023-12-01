"""Module for a TAPO Plug."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, cast

from ..credentials import Credentials
from ..emeterstatus import EmeterStatus
from ..smartdevice import DeviceType
from .tapodevice import TapoDevice
from ..modules import Emeter, Module

_LOGGER = logging.getLogger(__name__)


class TapoPlug(TapoDevice):
    """Class to represent a TAPO Plug."""

    def __init__(
        self,
        host: str,
        *,
        port: Optional[int] = None,
        credentials: Optional[Credentials] = None,
        timeout: Optional[int] = None,
    ) -> None:
        super().__init__(host, port=port, credentials=credentials, timeout=timeout)
        self._device_type = DeviceType.Plug
        self.modules: Dict[str, Any] = {}
        self.emeter_type = "emeter"
        self.modules["emeter"] = Emeter(self, self.emeter_type)

    @property  # type: ignore
    #@requires_update
    def has_emeter(self) -> bool:
        """Return that the plug has an emeter."""
        return True

    async def update(self, update_children: bool = True):
        """Call the device endpoint and update the device data."""
        await super().update(update_children)

        self._energy = await self.protocol.query("get_energy_usage")
        self._emeter = await self.protocol.query("get_current_power")

        self._data["energy"] = self._energy
        self._data["emeter"] = self._emeter

        _LOGGER.debug("Got an update: %s %s", self._energy, self._emeter)

        # Example of what a KP125M reports;
        # Got an update: {'today_runtime': 1327, 'month_runtime': 13511, 'today_energy': 537, 'month_energy': 5692, 'local_time': '2023-11-30 22:07:02', 'electricity_charge': [0, 0, 0], 'current_power': 1339} {'current_power': 1}

    @property
    def state_information(self) -> Dict[str, Any]:
        """Return the key state information."""
        return {
            **super().state_information,
            **{
                "On since": self.on_since,
                "auto_off_status": self._info.get("auto_off_status"),
                "auto_off_remain_time": self._info.get("auto_off_remain_time"),
            },
        }

    @property
    def emeter_realtime(self) -> EmeterStatus:
        """Get the emeter status."""
        return EmeterStatus({"power_mw": self._energy.get("current_power"),
                             "total": self._energy.get("today_energy") / 1000})

    @property
    def emeter_today(self) -> Optional[float]:
        """Get the emeter value for today."""
        return self._energy.get("today_energy") / 1000

    @property
    def emeter_this_month(self) -> Optional[float]:
        """Get the emeter value for this month."""
        return self._energy.get("month_energy") / 1000

    @property
    def on_since(self) -> Optional[datetime]:
        """Return the time that the device was turned on or None if turned off."""
        if not self._info.get("device_on"):
            return None
        on_time = cast(float, self._info.get("on_time"))
        return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)
