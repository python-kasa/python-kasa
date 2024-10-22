"""Module for smartcamera."""

from __future__ import annotations

import logging
from typing import Any

from ..device_type import DeviceType
from ..module import Module
from ..smart import SmartChildDevice, SmartDevice
from .modules.childdevice import ChildDevice
from .modules.device import DeviceModule
from .smartcameramodule import SmartCameraModule
from .smartcameraprotocol import _ChildCameraProtocolWrapper

_LOGGER = logging.getLogger(__name__)


class SmartCamera(SmartDevice):
    """Class for smart cameras."""

    # Modules that are called as part of the init procedure on first update
    FIRST_UPDATE_MODULES = {DeviceModule, ChildDevice}

    @staticmethod
    def _get_device_type_from_sysinfo(sysinfo: dict[str, Any]) -> DeviceType:
        """Find type to be displayed as a supported device category."""
        device_type = sysinfo["device_type"]
        if device_type[-3:] == "HUB":
            return DeviceType.Hub
        return DeviceType.Camera

    def _update_internal_info(self, info_resp):
        """Update the internal device info."""
        info = self._try_get_response(info_resp, "getDeviceInfo")
        self._info = self._map_info(info["device_info"])

    def _update_children_info(self):
        """Update the internal child device info from the parent info."""
        if child_info := self._try_get_response(
            self._last_update, "getChildDeviceList", {}
        ):
            for info in child_info["child_device_list"]:
                self._children[info["device_id"]]._update_internal_state(info)

    async def _initialize_children(self):
        """Initialize children for hubs."""
        if child_info := self._try_get_response(
            self._last_update, "getChildDeviceList", {}
        ):
            for info in child_info["child_device_list"]:
                if (
                    category := info.get("category")
                ) and category in SmartChildDevice.CHILD_DEVICE_TYPE_MAP:
                    child_id = info["device_id"]
                    child_protocol = _ChildCameraProtocolWrapper(
                        child_id, self.protocol
                    )
                    try:
                        initial_response = await child_protocol.query(
                            {"component_nego": None, "get_connect_cloud_state": None}
                        )
                        child_components = {
                            item["id"]: item["ver_code"]
                            for item in initial_response["component_nego"][
                                "component_list"
                            ]
                        }
                        self._children[child_id] = await SmartChildDevice.create(
                            parent=self,
                            child_info=info,
                            child_components=child_components,
                            protocol=child_protocol,
                            last_update=initial_response,
                        )
                    except Exception as ex:
                        _LOGGER.exception(
                            "Error initialising child %s: %s", child_id, ex
                        )
                        continue
                    self._children[child_id]._update_internal_state(info)
                else:
                    _LOGGER.debug("Child device type not supported: %s", info)

    async def _initialize_modules(self):
        """Initialize modules based on component negotiation response."""
        for mod in SmartCameraModule.REGISTERED_MODULES.values():
            module = mod(self, mod.NAME)
            self._modules[module.name] = module

    async def _initialize_features(self):
        """Initialize device features."""
        for module in self.modules.values():
            module._initialize_features()
            for feat in module._module_features.values():
                self._add_feature(feat)
        for child in self._children.values():
            await child._initialize_features()

    async def _query_setter_helper(
        self, method: str, module: str, section: str, params: dict | None = None
    ) -> Any:
        res = await self.protocol.query({method: {module: {section: params}}})

        return res

    async def _query_getter_helper(
        self, method: str, module: str, sections: str | list[str]
    ) -> Any:
        res = await self.protocol.query({method: {module: {"name": sections}}})

        return res

    async def _negotiate(self):
        """Perform initialization.

        We fetch the device info and the available components as early as possible.
        If the device reports supporting child devices, they are also initialized.
        """
        initial_query = {
            "getDeviceInfo": {"device_info": {"name": ["basic_info", "info"]}},
            # "getLensMaskConfig": {"lens_mask": {"name": ["lens_mask_info"]}},
            "getChildDeviceList": {"childControl": {"start_index": 0}},
        }
        resp = await self.protocol.query(initial_query)
        self._last_update.update(resp)
        self._update_internal_info(resp)
        await self._initialize_children()

    def _map_info(self, device_info: dict) -> dict:
        basic_info = device_info["basic_info"]
        return {
            "model": basic_info["device_model"],
            "device_type": basic_info["device_type"],
            "alias": basic_info["device_alias"],
            "fw_ver": basic_info["sw_version"],
            "hw_ver": basic_info["hw_version"],
            "mac": basic_info["mac"],
            "hwId": basic_info["hw_id"],
            "oem_id": basic_info["oem_id"],
        }

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        if (camera := self.modules.get(Module.Camera)) and not camera.disabled:
            return camera.is_on
        return True

    async def set_state(self, on: bool):
        """Set the device state."""
        if (camera := self.modules.get(Module.Camera)) and not camera.disabled:
            await camera.set_state(on)

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        if self._device_type == DeviceType.Unknown:
            self._device_type = self._get_device_type_from_sysinfo(self._info)
        return self._device_type

    @property
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""
        if self._info:
            return self._info.get("alias")
        return None

    # setDeviceInfo sets the device_name
    # "setDeviceInfo": {"device_info": {"basic_info": {"device_name": alias}}},
    async def set_alias(self, alias: str):
        """Set the device name (alias)."""
        return await self.protocol.query(
            {
                "setDeviceAlias": {"system": {"sys": {"dev_alias": alias}}},
            }
        )

    @property
    def hw_info(self) -> dict:
        """Return hardware info for the device."""
        return {
            "sw_ver": self._info.get("hw_ver"),
            "hw_ver": self._info.get("fw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("hwId"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }
