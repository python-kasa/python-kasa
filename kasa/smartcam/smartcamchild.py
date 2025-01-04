"""Child device implementation."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..device import DeviceInfo
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..protocols.smartcamprotocol import _ChildCameraProtocolWrapper
from ..protocols.smartprotocol import SmartProtocol
from ..smart.smartdevice import ComponentsRaw, SmartDevice
from ..smart.smartmodule import SmartModule
from .smartcamdevice import SmartCamDevice

_LOGGER = logging.getLogger(__name__)

CHILD_INFO_FROM_PARENT = "child_info_from_parent"


class SmartCamChild(SmartCamDevice):
    """Presentation of a child device.

    This wraps the protocol communications and sets internal data for the child.
    """

    CHILD_DEVICE_TYPE_MAP = {
        ("camera", "SMART.TAPODOORBELL"): DeviceType.Camera,
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
        self._id = info["device_id"]
        _protocol = protocol or _ChildCameraProtocolWrapper(self._id, parent.protocol)
        super().__init__(parent.host, config=parent.config, protocol=_protocol)
        self._parent = parent
        self._update_internal_state(info)
        self._components_raw = component_info_raw
        self._components = self._parse_components(self._components_raw)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info.

        Child device does not have it info and components in _last_update so
        this overrides the base implementation to call _get_device_info with
        info and components combined as they would be in _last_update.
        """
        return self._get_device_info(
            {
                CHILD_INFO_FROM_PARENT: self._info,
            },
            None,
        )

    def _map_info(self, device_info: dict) -> dict:
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

    @staticmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get model information for a device."""
        if not (cifp := info.get(CHILD_INFO_FROM_PARENT)):
            return SmartCamDevice._get_device_info(info, discovery_info)

        model = cifp["model"]
        device_type = SmartCamDevice._get_device_type_from_sysinfo(cifp)
        fw_version_full = cifp["fw_ver"]
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

    async def update(self, update_children: bool = True) -> None:
        """Update child module info.

        The parent updates our internal info so just update modules with
        their own queries.
        """
        await self._update(update_children)

    async def _update(self, update_children: bool = True) -> None:
        """Update child module info.

        Internal implementation to allow patching of public update in the cli
        or test framework.
        """
        now = time.monotonic()
        module_queries: list[SmartModule] = []
        req: dict[str, Any] = {}
        for module in self.modules.values():
            if module.disabled is False and (mod_query := module.query()):
                module_queries.append(module)
                req.update(mod_query)
        if req:
            self._last_update = await self.protocol.query(req)

        for module in self.modules.values():
            await self._handle_module_post_update(
                module, now, had_query=module in module_queries
            )
        self._last_update_time = now

    @classmethod
    async def create(
        cls,
        parent: SmartCamDevice,
        child_info: dict,
        child_components_raw: ComponentsRaw,
        protocol: SmartProtocol | None = None,
        *,
        last_update: dict | None = None,
    ) -> SmartDevice:
        """Create a child device based on device info and component listing.

        If creating a smart child from a different protocol, i.e. a camera hub,
        protocol: SmartProtocol and last_update should be provided as per the
        FIRST_UPDATE_MODULES expected by the update cycle as these cannot be
        derived from the parent.
        """
        child: SmartCamChild = cls(
            parent, child_info, child_components_raw, protocol=protocol
        )
        if last_update:
            child._last_update = last_update
        await child._initialize_modules()
        return child

    @property
    def device_type(self) -> DeviceType:
        """Return child device type."""
        if self._device_type is not DeviceType.Unknown:
            return self._device_type

        if (
            self.sys_info
            and (category := self.sys_info.get("category"))
            and (device_family := self.sys_info.get("device_type"))
        ):
            dev_type = self.CHILD_DEVICE_TYPE_MAP.get((category, device_family))
            if dev_type is None:
                _LOGGER.warning(
                    "Unknown child device type %s for model %s, please open issue",
                    category,
                    self.model,
                )
                self._device_type = DeviceType.Unknown
            else:
                self._device_type = dev_type

        return self._device_type

    def __repr__(self) -> str:
        if not self._parent:
            return f"<{self.device_type}(child) without parent>"
        if not self._parent._last_update:
            return f"<{self.device_type}(child) of {self._parent}>"
        return f"<{self.device_type} {self.alias} ({self.model}) of {self._parent}>"
