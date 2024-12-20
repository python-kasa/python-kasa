"""Module for cameras."""

from __future__ import annotations

import logging
from datetime import datetime, tzinfo

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..protocols import BaseProtocol
from .iotdevice import IotDevice

_LOGGER = logging.getLogger(__name__)


class IotCamera(IotDevice):
    """Representation of a TP-Link Camera."""

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: BaseProtocol | None = None,
    ) -> None:
        super().__init__(host=host, config=config, protocol=protocol)
        self._device_type = DeviceType.Camera

    @property
    def time(self) -> datetime:
        """Get the camera's time."""
        return datetime.fromtimestamp(self.sys_info["system_time"])

    @property
    def timezone(self) -> tzinfo:
        """Get the camera's timezone."""
        return None  # type: ignore

    @property  # type: ignore
    def is_on(self) -> bool:
        """Return whether device is on."""
        return True
