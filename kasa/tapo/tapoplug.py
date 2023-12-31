"""Module for a TAPO Plug."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, cast

from ..deviceconfig import DeviceConfig
from ..protocol import TPLinkProtocol
from ..smartdevice import DeviceType
from .tapodevice import TapoDevice

_LOGGER = logging.getLogger(__name__)


class TapoPlug(TapoDevice):
    """Class to represent a TAPO Plug."""

    def __init__(
        self,
        host: str,
        *,
        config: Optional[DeviceConfig] = None,
        protocol: Optional[TPLinkProtocol] = None,
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

    @property
    def on_since(self) -> Optional[datetime]:
        """Return the time that the device was turned on or None if turned off."""
        if not self._info.get("device_on"):
            return None
        on_time = cast(float, self._info.get("on_time"))
        return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)
