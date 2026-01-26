"""Module for SmartCamDevice."""

from __future__ import annotations

import base64
import logging
from typing import Any, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from ..device import DeviceInfo, WifiNetwork
from ..device_type import DeviceType
from ..deviceconfig import DeviceConfig
from ..exceptions import AuthenticationError, DeviceError, KasaException
from ..module import Module
from ..protocols import SmartProtocol
from ..protocols.smartcamprotocol import _ChildCameraProtocolWrapper
from ..smart import SmartChildDevice, SmartDevice
from ..smart.smartdevice import ComponentsRaw
from .modules import ChildDevice, DeviceModule
from .smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class SmartCamDevice(SmartDevice):
    """Class for smart cameras."""

    # Modules that are called as part of the init procedure on first update
    FIRST_UPDATE_MODULES = {DeviceModule, ChildDevice}

    STATIC_PUBLIC_KEY_B64 = (
        "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC4D6i0oD/Ga5qb//RfSe8MrPVI"
        "rMIGecCxkcGWGj9kxxk74qQNq8XUuXoy2PczQ30BpiRHrlkbtBEPeWLpq85tfubT"
        "UjhBz1NPNvWrC88uaYVGvzNpgzZOqDC35961uPTuvdUa8vztcUQjEZy16WbmetRj"
        "URFIiWJgFCmemyYVbQIDAQAB"
    )

    def __init__(
        self,
        host: str,
        *,
        config: DeviceConfig | None = None,
        protocol: SmartProtocol | None = None,
    ) -> None:
        super().__init__(host, config=config, protocol=protocol)
        self._public_key: str | None = None
        self._networks: list[WifiNetwork] = []

    @staticmethod
    def _get_device_type_from_sysinfo(sysinfo: dict[str, Any]) -> DeviceType:
        """Find type to be displayed as a supported device category."""
        if not (device_type := sysinfo.get("device_type")):
            return DeviceType.Unknown

        if device_type.endswith("HUB"):
            return DeviceType.Hub

        if "DOORBELL" in device_type:
            return DeviceType.Doorbell

        return DeviceType.Camera

    @staticmethod
    def _get_device_info(
        info: dict[str, Any], discovery_info: dict[str, Any] | None
    ) -> DeviceInfo:
        """Get model information for a device."""
        basic_info = info["getDeviceInfo"]["device_info"]["basic_info"]
        short_name = basic_info["device_model"]
        long_name = discovery_info["device_model"] if discovery_info else short_name
        device_type = SmartCamDevice._get_device_type_from_sysinfo(basic_info)
        fw_version_full = basic_info["sw_version"]
        if " " in fw_version_full:
            firmware_version, firmware_build = fw_version_full.split(" ", maxsplit=1)
        else:
            firmware_version, firmware_build = fw_version_full, None
        return DeviceInfo(
            short_name=basic_info["device_model"],
            long_name=long_name,
            brand="tapo",
            device_family=basic_info["device_type"],
            device_type=device_type,
            hardware_version=basic_info["hw_version"],
            firmware_version=firmware_version,
            firmware_build=firmware_build,
            requires_auth=True,
            region=basic_info.get("region"),
        )

    def _update_internal_info(self, info_resp: dict) -> None:
        """Update the internal device info."""
        info = self._try_get_response(info_resp, "getDeviceInfo")
        self._info = self._map_info(info["device_info"])

    def _update_internal_state(self, info: dict[str, Any]) -> None:
        """Update the internal info state.

        This is used by the parent to push updates to its children.
        """
        self._info = self._map_info(info)

    async def _update_children_info(self) -> bool:
        """Update the internal child device info from the parent info.

        Return true if children added or deleted.
        """
        changed = False
        if child_info := self._try_get_response(
            self._last_update, "getChildDeviceList", {}
        ):
            changed = await self._create_delete_children(
                child_info, self._last_update["getChildDeviceComponentList"]
            )

            for info in child_info["child_device_list"]:
                child_id = info.get("device_id")
                if child_id not in self._children:
                    # _create_delete_children has already logged a message
                    continue

                self._children[child_id]._update_internal_state(info)

        return changed

    async def _initialize_smart_child(
        self, info: dict, child_components_raw: ComponentsRaw
    ) -> SmartDevice:
        """Initialize a smart child device attached to a smartcam device."""
        child_id = info["device_id"]
        child_protocol = _ChildCameraProtocolWrapper(child_id, self.protocol)
        try:
            initial_response = await child_protocol.query(
                {"get_connect_cloud_state": None}
            )
        except Exception as ex:
            _LOGGER.exception("Error initialising child %s: %s", child_id, ex)

        return await SmartChildDevice.create(
            parent=self,
            child_info=info,
            child_components_raw=child_components_raw,
            protocol=child_protocol,
            last_update=initial_response,
        )

    async def _initialize_smartcam_child(
        self, info: dict, child_components_raw: ComponentsRaw
    ) -> SmartDevice:
        """Initialize a smart child device attached to a smartcam device."""
        child_id = info["device_id"]
        child_protocol = _ChildCameraProtocolWrapper(child_id, self.protocol)

        app_component_list = {
            "app_component_list": child_components_raw["component_list"]
        }
        from .smartcamchild import SmartCamChild

        return await SmartCamChild.create(
            parent=self,
            child_info=info,
            child_components_raw=app_component_list,
            protocol=child_protocol,
        )

    async def _initialize_children(self) -> None:
        """Initialize children for hubs."""
        child_info_query = {
            "getChildDeviceList": {"childControl": {"start_index": 0}},
            "getChildDeviceComponentList": {"childControl": {"start_index": 0}},
        }
        resp = await self.protocol.query(child_info_query)
        self.internal_state.update(resp)

    async def _try_create_child(
        self, info: dict, child_components: dict
    ) -> SmartDevice | None:
        if not (category := info.get("category")):
            return None

        # Smart
        if category in SmartChildDevice.CHILD_DEVICE_TYPE_MAP:
            return await self._initialize_smart_child(info, child_components)
        # Smartcam
        from .smartcamchild import SmartCamChild

        if category in SmartCamChild.CHILD_DEVICE_TYPE_MAP:
            return await self._initialize_smartcam_child(info, child_components)

        return None

    async def _initialize_modules(self) -> None:
        """Initialize modules based on component negotiation response."""
        for mod in SmartCamModule.REGISTERED_MODULES.values():
            if (
                mod.REQUIRED_COMPONENT
                and mod.REQUIRED_COMPONENT not in self._components
            ):
                continue
            module = mod(self, mod._module_name())
            if await module._check_supported():
                self._modules[module.name] = module

    async def _initialize_features(self) -> None:
        """Initialize device features."""
        for module in self.modules.values():
            module._initialize_features()
            for feat in module._module_features.values():
                self._add_feature(feat)

    async def _query_setter_helper(
        self, method: str, module: str, section: str, params: dict | None = None
    ) -> dict:
        res = await self.protocol.query({method: {module: {section: params}}})

        return res

    @staticmethod
    def _parse_components(components_raw: ComponentsRaw) -> dict[str, int]:
        return {
            str(comp["name"]): int(comp["version"])
            for comp in components_raw["app_component_list"]
        }

    async def _negotiate(self) -> None:
        """Perform initialization.

        We fetch the device info and the available components as early as possible.
        If the device reports supporting child devices, they are also initialized.
        """
        initial_query = {
            "getDeviceInfo": {"device_info": {"name": ["basic_info", "info"]}},
            "getAppComponentList": {"app_component": {"name": "app_component_list"}},
            "getConnectionType": {"network": {"get_connection_type": {}}},
        }
        resp = await self.protocol.query(initial_query)
        self._last_update.update(resp)
        self._update_internal_info(resp)

        self._components_raw = cast(
            ComponentsRaw, resp["getAppComponentList"]["app_component"]
        )
        self._components = self._parse_components(self._components_raw)

        if "childControl" in self._components and not self.children:
            await self._initialize_children()

    def _map_info(self, device_info: dict) -> dict:
        """Map the basic keys to the keys used by SmartDevices."""
        basic_info = device_info["basic_info"]
        mappings = {
            "device_model": "model",
            "device_alias": "alias",
            "sw_version": "fw_ver",
            "hw_version": "hw_ver",
            "hw_id": "hwId",
            "dev_id": "device_id",
        }
        return {mappings.get(k, k): v for k, v in basic_info.items()}

    @property
    def is_on(self) -> bool:
        """Return true if the device is on."""
        if (camera := self.modules.get(Module.Camera)) and not camera.disabled:
            return camera.is_on

        return True

    async def set_state(self, on: bool) -> dict:
        """Set the device state."""
        if (camera := self.modules.get(Module.Camera)) and not camera.disabled:
            return await camera.set_state(on)

        return {}

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        if self._device_type == DeviceType.Unknown and self._info:
            self._device_type = self._get_device_type_from_sysinfo(self._info)
        return self._device_type

    @property
    def alias(self) -> str | None:
        """Returns the device alias or nickname."""
        if self._info:
            return self._info.get("alias")
        return None

    async def set_alias(self, alias: str) -> dict:
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
            "sw_ver": self._info.get("fw_ver"),
            "hw_ver": self._info.get("hw_ver"),
            "mac": self._info.get("mac"),
            "type": self._info.get("type"),
            "hwId": self._info.get("hwId"),
            "dev_name": self.alias,
            "oemId": self._info.get("oem_id"),
        }

    @property
    def rssi(self) -> int | None:
        """Return the device id."""
        return self.modules[SmartCamModule.SmartCamDeviceModule].rssi

    async def wifi_scan(self) -> list[WifiNetwork]:
        """Scan for available wifi networks."""

        def _net_for_scan_info(res: dict) -> WifiNetwork:
            return WifiNetwork(
                ssid=res["ssid"],
                auth=res["auth"],
                encryption=res["encryption"],
                channel=res["channel"],
                rssi=res["rssi"],
                bssid=res["bssid"],
            )

        _LOGGER.debug("Querying networks")

        resp = await self._query_helper("scanApList", {"onboarding": {"scan": {}}})
        scan_data: dict = resp["scanApList"]["onboarding"]["scan"]
        self._public_key = scan_data.get("publicKey", "")
        self._networks = [_net_for_scan_info(net) for net in scan_data["ap_list"]]
        return self._networks

    async def wifi_join(
        self, ssid: str, password: str, keytype: str = "wpa2_psk"
    ) -> dict:
        """Join the given wifi network.

        This method returns nothing as the device tries to activate the new
        settings immediately instead of responding to the request.

        If joining the network fails, the device will return to the previous state
        after some delay.
        """
        if not self.credentials:
            raise AuthenticationError("Device requires authentication.")

        if not self._networks:
            await self.wifi_scan()
        net = next(
            (n for n in self._networks if getattr(n, "ssid", None) == ssid), None
        )
        if net is None:
            raise DeviceError(f"Network with SSID '{ssid}' not found.")

        public_key_b64 = self._public_key or self.STATIC_PUBLIC_KEY_B64
        key_bytes = base64.b64decode(public_key_b64)
        public_key = serialization.load_der_public_key(key_bytes)
        if not isinstance(public_key, RSAPublicKey):
            raise TypeError("Loaded public key is not an RSA public key")
        encrypted = public_key.encrypt(password.encode(), padding.PKCS1v15())
        encrypted_password = base64.b64encode(encrypted).decode()

        payload = {
            "onboarding": {
                "connect": {
                    "auth": net.auth,
                    "bssid": net.bssid,
                    "encryption": net.encryption,
                    "password": encrypted_password,
                    "rssi": net.rssi,
                    "ssid": net.ssid,
                }
            }
        }

        # The device does not respond to the request but changes the settings
        # immediately which causes us to timeout.
        # Thus, We limit retries and suppress the raised exception as useless.
        try:
            return await self.protocol.query({"connectAp": payload}, retry_count=0)
        except DeviceError:
            raise  # Re-raise on device-reported errors
        except KasaException:
            _LOGGER.debug(
                "Received a kasa exception for wifi join, but this is expected"
            )
            return {}
