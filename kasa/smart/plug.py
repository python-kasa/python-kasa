"""Module for a TAPO Plug."""
import logging
from typing import Any, Dict, Optional

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..plug import Plug
from ..smartprotocol import SmartProtocol
from .device import SmartDevice

_LOGGER = logging.getLogger(__name__)


class SmartPlug(SmartDevice, Plug):
    """Class to represent a TAPO Plug."""

    def __init__(
        self,
        host: str,
        *,
        config: Optional[DeviceConfig] = None,
        protocol: Optional[SmartProtocol] = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.Plug

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
