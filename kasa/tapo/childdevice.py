"""Child device implementation."""
from typing import Optional

from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..smartprotocol import SmartProtocol, _ChildProtocolWrapper
from .tapodevice import TapoDevice


class ChildDevice(TapoDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    def __init__(
        self,
        parent: TapoDevice,
        child_id: str,
        config: Optional[DeviceConfig] = None,
        protocol: Optional[SmartProtocol] = None,
    ) -> None:
        super().__init__(parent.host, config=parent.config, protocol=parent.protocol)
        self._parent = parent
        self._id = child_id
        self.protocol = _ChildProtocolWrapper(child_id, parent.protocol)
        # TODO: remove the assignment after modularization is done,
        #  currently required to allow accessing time-related properties
        self._time = parent._time
        self._device_type = DeviceType.StripSocket

    async def update(self, update_children: bool = True):
        """Noop update. The parent updates our internals."""

    def update_internal_state(self, info):
        """Set internal state for the child."""
        # TODO: cleanup the _last_update, _sys_info, _info, _data mess.
        self._last_update = self._sys_info = self._info = info

    def __repr__(self):
        return f"<ChildDevice {self.alias} of {self._parent}>"
