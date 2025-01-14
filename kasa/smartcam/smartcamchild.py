"""Child device implementation."""

from __future__ import annotations

import logging
from typing import Any

from ..device import DeviceInfo
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..protocols.smartcamprotocol import _ChildCameraProtocolWrapper
from ..protocols.smartprotocol import SmartProtocol
from ..smart.smartchilddevice import SmartChildDevice
from ..smart.smartdevice import ComponentsRaw, SmartDevice
from .smartcamdevice import SmartCamDevice

_LOGGER = logging.getLogger(__name__)

# SmartCamChild devices have a different info format from getChildDeviceInfo
# than when querying getDeviceInfo directly on the child.
# As _get_device_info is also called by dump_devtools and generate_supported
# this key will be expected by _get_device_info
CHILD_INFO_FROM_PARENT = "child_info_from_parent"


class SmartCamChild(SmartChildDevice, SmartCamDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    CHILD_DEVICE_TYPE_MAP = {
        "camera": DeviceType.Camera,
    }

    def __init__(
        self,
        parent: SmartDevice,
        info: dict,
        component_info_raw: ComponentsRaw,
        *,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        _protocol = protocol or _ChildCameraProtocolWrapper(
            info["device_id"], parent.protocol
        )
        super().__init__(parent, info, component_info_raw, protocol=_protocol)
        self._child_info_from_parent: dict = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info.

        Child device does not have it info and components in _last_update so
        this overrides the base implementation to call _get_device_info with
        info and components combined as they would be in _last_update.
        """
        return self._get_device_info(
            {
                CHILD_INFO_FROM_PARENT: self._child_info_from_parent,
            },
            None,
        )

    def _map_child_info_from_parent(self, device_info: dict) -> dict:
        return {
            "model": device_info["device_model"],
            "device_type": device_info["device_type"],
            "alias": device_info["alias"],
            "fw_ver": device_info["sw_ver"],
            "hw_ver": device_info["hw_ver"],
            "mac": device_info["mac"],
            "hwId": device_info.get("hw_id"),
            "oem_id": device_info["oem_id"],
            "device_id": device_info["device_id"],
        }

    def _update_internal_state(self, info: dict[str, Any]) -> None:
        """Update the internal info state.

        This is used by the parent to push updates to its children.
        """
        # smartcam children have info with different keys to their own
        # getDeviceInfo queries
        self._child_info_from_parent = info

        # self._info will have the values normalized across smart and smartcam
        # devices
        self._info = self._map_child_info_from_parent(info)

    @staticmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get model information for a device."""
        if not (cifp := info.get(CHILD_INFO_FROM_PARENT)):
            return SmartCamDevice._get_device_info(info, discovery_info)

        model = cifp["device_model"]
        device_type = SmartCamDevice._get_device_type_from_sysinfo(cifp)
        fw_version_full = cifp["sw_ver"]
        firmware_version, firmware_build = fw_version_full.split(" ", maxsplit=1)
        return DeviceInfo(
            short_name=model,
            long_name=model,
            brand="tapo",
            device_family=cifp["device_type"],
            device_type=device_type,
            hardware_version=cifp["hw_ver"],
            firmware_version=firmware_version,
            firmware_build=firmware_build,
            requires_auth=True,
            region=cifp.get("region"),
        )
