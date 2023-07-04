"""Module for smart plugs (HS100, HS110, ..)."""
import logging
from typing import Any, Dict, List, Optional, Set

import asyncio

from kasa.modules import Antitheft, Cloud, Schedule, Time, Usage
from kasa.smartdevice import DeviceType, SmartDevice
from kasa.exceptions import SmartDeviceAuthenticationException, SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class UnauthenticatedDevice(SmartDevice):
    r"""Representation of an UnauthenticatedDevice, i.e. where initial discovery information is available but a call to get_sysinfo failed."""

    UNKNOWN_VALUE_STRING = "Unknown"

    def __init__(self, host: str, protocol, unauthenticated_info) -> None:
        super().__init__(host, protocol)

        self._device_type = DeviceType.Unknown
        self.isauthenticated = False
        self.triedauthentication = False
        self.authentication_callback = None
        self.wrapped_sys_info = None
        self.unauthenticated_info = unauthenticated_info

    @property  # type: ignore
    def is_on(self) -> bool:
        """Return whether device is on."""
        return True

    @property
    def internal_state(self) -> Any:
        """Return the internal state of the instance.

        The returned object contains the raw results from the last update call.
        This should only be used for debugging purposes.
        """
        return self.unauthenticated_info

    async def add_success_callback(self, task, callback, authenticating_device):
        result = await task
        await callback(authenticating_device)
        return result

    async def _try_authenticate(self):
        try:
            self.wrapped_sys_info = await self.protocol.try_query_discovery_info()
            if self.wrapped_sys_info is not None:
                self.isauthenticated = True
            else:
                self.isauthenticated = False

        except SmartDeviceAuthenticationException as ex:
            self.isauthenticated = False
        finally:
            self.triedauthentication = True

    def try_authenticate(self, authentication_callback):
        """Attempt to authenticate and callback on a authentication_callback with self instance as the parameter"""
        self.authentication_callback = authentication_callback

        task = asyncio.create_task(self._try_authenticate())
        done_task = asyncio.create_task(
            self.add_success_callback(task, self.authentication_callback, self)
        )

    async def update(self, update_children: bool = True):
        """Does nothing"""
        pass

    @property  # type: ignore
    def led(self) -> bool:
        """Return the state of the led."""
        return self.UNKNOWN_VALUE_STRING

    @property  # type: ignore
    def state_information(self) -> Dict[str, Any]:
        """Return switch-specific state information."""

        stateinfo = {
            "device_owner": self.unauthenticated_info["result"]["owner"],
            "auth_owner": self.protocol.local_auth_owner,
            "mgt_encrypt_schm": self.unauthenticated_info["result"]["mgt_encrypt_schm"],
            "device_type": self.unauthenticated_info["result"]["device_type"],
            "device_model": self.unauthenticated_info["result"]["device_model"],
        }
        return stateinfo

    @property  # type: ignore
    def features(self) -> Set[str]:
        """Return a set of features that the device supports."""
        return set()

    @property  # type: ignore
    def supported_modules(self) -> List[str]:
        """Return a set of modules supported by the device."""
        # TODO: this should rather be called `features`, but we don't want to break
        #       the API now. Maybe just deprecate it and point the users to use this?
        return list()

    @property  # type: ignore
    def has_emeter(self) -> bool:
        return False

    async def _modular_update(self, req: dict) -> None:
        """Execute an update query."""
        pass

    @property  # type: ignore
    def sys_info(self) -> Dict[str, Any]:
        """Return system information."""
        return self.UNKNOWN_VALUE_STRING

    @property  # type: ignore
    def model(self) -> str:
        """Return device model."""
        return str(self.unauthenticated_info["result"]["device_model"])

    @property  # type: ignore
    def alias(self) -> str:
        """Return device name (alias)."""
        return "Unauthenticated Device"

    @property  # type: ignore
    def time(self) -> Any:
        """Return current time from the device."""
        return None

    @property  # type: ignore
    def timezone(self) -> Dict:
        """Return the current timezone."""
        return None

    @property  # type: ignore
    def hw_info(self) -> Dict:
        """Return hardware information.

        This returns just a selection of sysinfo keys that are related to hardware.
        """
        keyvals = {
            "sw_ver": self.UNKNOWN_VALUE_STRING,
            "hw_ver": self.unauthenticated_info["result"]["hw_ver"],
            "mac": self.unauthenticated_info["result"]["mac"],
            "mic_mac": self.UNKNOWN_VALUE_STRING,
            "type": self.UNKNOWN_VALUE_STRING,
            "mic_type": self.UNKNOWN_VALUE_STRING,
            "hwId": self.UNKNOWN_VALUE_STRING,
            "fwId": self.UNKNOWN_VALUE_STRING,
            "oemId": self.UNKNOWN_VALUE_STRING,
            "dev_name": self.UNKNOWN_VALUE_STRING,
        }

        return keyvals

    @property  # type: ignore
    def location(self) -> Dict:
        """Return geographical location."""
        return None

    @property  # type: ignore
    def rssi(self) -> Optional[int]:
        return None

    @property  # type: ignore
    def mac(self) -> str:
        """Return mac address.

        :return: mac address in hexadecimal with colons, e.g. 01:23:45:67:89:ab
        """

        mac = self.unauthenticated_info["result"]["mac"]
        if not mac:
            raise SmartDeviceException(
                "Unknown mac, please submit a bug report with sys_info output."
            )

        if ":" not in mac:
            mac = str.replace(mac, "-", "")
            mac = ":".join(format(s, "02x") for s in bytes.fromhex(mac))

        return mac

    @property  # type: ignore
    def device_id(self) -> str:
        """Return unique ID for the device."""
        return self.unauthenticated_info["result"]["device_id"]

    @property
    def device_type(self) -> DeviceType:
        """Return the device type."""
        return DeviceType.Unknown

    @property
    def is_bulb(self) -> bool:
        """Return True if the device is a bulb."""
        return False

    @property
    def is_light_strip(self) -> bool:
        """Return True if the device is a led strip."""
        return False

    @property
    def is_plug(self) -> bool:
        """Return True if the device is a plug."""
        return False

    @property
    def is_strip(self) -> bool:
        """Return True if the device is a strip."""
        return False

    @property
    def is_strip_socket(self) -> bool:
        """Return True if the device is a strip socket."""
        return False

    @property
    def is_dimmer(self) -> bool:
        """Return True if the device is a dimmer."""
        return False

    @property
    def is_dimmable(self) -> bool:
        """Return  True if the device is dimmable."""
        return False

    @property
    def is_variable_color_temp(self) -> bool:
        """Return True if the device supports color temperature."""
        return False

    @property
    def is_color(self) -> bool:
        """Return True if the device supports color changes."""
        return False

    @property
    def internal_state(self) -> Any:
        """Return the internal state of the instance.

        The returned object contains the raw results from the discovery call.
        This should only be used for debugging purposes.
        """
        return self.unauthenticated_info
