"""Child device implementation."""
from typing import Dict, Optional, Union

from ..deviceconfig import DeviceConfig
from ..exceptions import SmartDeviceException
from ..smartprotocol import SmartProtocol
from .tapodevice import TapoDevice


class ChildProtocolWrapper(SmartProtocol):
    """Protocol wrapper for controlling child devices.

    This wraps requests send to child devices with the necessary wrapping.
    """

    def __init__(self, device: TapoDevice, protocol: SmartProtocol):
        self._device = device
        self._protocol = protocol
        self._transport = protocol._transport

    async def query(self, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Wrap request inside control_child envelope."""
        method, params = self._protocol.get_method_and_params_for_request(request)
        request_data = {
            "method": method,
            "params": params,
        }
        wrapped_payload = {
            "control_child": {
                "device_id": self._device._info["device_id"],
                "requestData": request_data,
            }
        }

        return await self._protocol.query(wrapped_payload, retry_count)

    async def close(self) -> None:
        """Do nothing as the parent owns the protocol."""


class ChildDevice(TapoDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    def __init__(
        self,
        parent: TapoDevice,
        child_id: int,
        config: Optional[DeviceConfig] = None,
        protocol: Optional[SmartProtocol] = None,
    ) -> None:
        super().__init__(parent.host, config=parent.config, protocol=parent.protocol)
        self._parent = parent
        self._id = child_id
        self.protocol = ChildProtocolWrapper(self, parent.protocol)

    async def update(self, update_children: bool = True):
        """We just set the info here accordingly."""

        def _get_child_info() -> Dict:
            """Return the subdevice information for this device."""
            for child in self._parent._last_update["child_info"]["child_device_list"]:
                if child["position"] == self._id:
                    return child

            raise SmartDeviceException(
                f"Unable to find child device with position {self._id}"
            )

        self._last_update = self._sys_info = self._info = _get_child_info()

    def __repr__(self):
        return f"<ChildDevice {self.alias} of {self._parent}>"
