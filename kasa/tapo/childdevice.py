"""Child device implementation."""
from typing import Dict, Optional

from ..deviceconfig import DeviceConfig
from ..exceptions import SmartDeviceException
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

    async def update(self, update_children: bool = True):
        """We just set the info here accordingly."""

        def _get_child_info() -> Dict:
            """Return the subdevice information for this device."""
            for child in self._parent._last_update["child_info"]["child_device_list"]:
                if child["device_id"] == self._id:
                    return child

            raise SmartDeviceException(
                f"Unable to find child device with id {self._id}"
            )

        self._last_update = self._sys_info = self._info = _get_child_info()

    def __repr__(self):
        return f"<ChildDevice {self.alias} of {self._parent}>"
