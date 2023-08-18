import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set

from plugp100.api.plug_device import PlugDevice
from plugp100.api.tapo_client import TapoClient
from plugp100.responses.device_state import DeviceInfo, PlugDeviceState
from plugp100.responses.device_usage_info import DeviceUsageInfo
from plugp100.responses.energy_info import EnergyInfo
from plugp100.responses.power_info import PowerInfo
from plugp100.responses.time_info import TimeInfo

from . import EmeterStatus
from .smartdevice import DeviceType, SmartDevice
from .smartplug import SmartPlug

_LOGGER = logging.getLogger(__name__)


# TODO: there should be a baseclass for plugs that does not initialize modules etc. that are related only to some implementations
class TapoPlug(SmartPlug):
    def __init__(self, host: str, *, port: Optional[int] = None) -> None:
        # TODO: we are calling smartdevice here to avoid smartplug internal handling
        SmartDevice.__init__(self, host, port=port)
        # TODO: this is needed as we don't call smartplug ctor
        self._device_type = DeviceType.Plug
        env = os.environ
        self._tapo_client = TapoClient(
            env["KASA_TAPO_EMAIL"], env["KASA_TAPO_PASSWORD"]
        )
        self._tapo_device = PlugDevice(self._tapo_client, self.host)
        self._state = None

    async def update(self, update_children: bool = True):
        if self._state is None:
            await self._tapo_device.login()

        # TODO: check for success as
        self._state = (await self._tapo_device.get_state()).value
        self._info: DeviceInfo = self._state.info

        self._usage: DeviceUsageInfo = (
            await self._tapo_device.get_device_usage()
        ).value
        self._energy: EnergyInfo = (await self._tapo_device.get_energy_usage()).value
        self._emeter: PowerInfo = (await self._tapo_device.get_current_power()).value
        self._time: TimeInfo = (await self._tapo_device.get_device_time()).value

        self._last_update = self._data = {
            "state": self._state,
            "usage": self._usage,
            "emeter": self._emeter,
            "energy": self._energy,
            "time": self._time,
        }

        _LOGGER.debug("Got an update: %s", self._data)

    @property
    def sys_info(self) -> Dict[str, Any]:
        return self._state

    @property
    def model(self) -> str:
        return self._info.model

    @property
    def alias(self) -> str:
        return self._info.nickname

    @property
    def time(self) -> datetime:
        return self._time.local_time()

    @property
    def timezone(self) -> Dict:
        return {"timezone": self._info.timezone, "timediff": self._info.time_difference}

    def has_emeter(self) -> bool:
        return True

    @property
    def emeter_realtime(self) -> EmeterStatus:
        return EmeterStatus({"power_mw": self._energy.current_power})

    @property
    def emeter_today(self) -> Optional[float]:
        return None

    @property
    def emeter_this_month(self) -> Optional[float]:
        return None

    @property
    def hw_info(self) -> Dict:
        # TODO: check that the keys match to kasa-infos
        return {
            "sw_ver": self._info.firmware_version,
            "hw_ver": self._info.hardware_version,
            "mac": self._info.mac,
            "type": self._info.type,
            "hwId": self._info.device_id,
            "dev_name": self._info.nickname,
            "oemId": self._info.oem_id,
        }

    @property
    def location(self) -> Dict:
        loc = {
            "latitude": self._info.latitude / 10_000,
            "longitude": self._info.longitude / 10_000,
        }
        return loc

    @property
    def rssi(self) -> Optional[int]:
        return self._info.rssi

    @property
    def mac(self) -> str:
        return self._info.mac.replace("-", ":")

    @property
    def device_id(self) -> str:
        return self._info.device_id

    @property
    def internal_state(self) -> Any:
        return self._data

    @property
    def is_on(self) -> bool:
        return self._state.device_on

    async def turn_on(self, **kwargs):
        return await self._tapo_device.on()

    async def turn_off(self, **kwargs):
        return await self._tapo_device.off()

    async def _query_helper(
        self, target: str, cmd: str, arg: Optional[Dict] = None, child_ids=None
    ) -> Any:
        res = await self._tapo_device.raw_command(cmd, arg)
        if res.is_left():
            raise res.error
        return res.value

    @property
    def led(self) -> bool:
        return None

    async def set_led(self, state: bool):
        return await super().set_led(state)

    @property
    def on_since(self) -> Optional[datetime]:
        on_time = self._info.on_time
        return datetime.now().replace(microsecond=0) - timedelta(seconds=on_time)

    @property
    def state_information(self) -> Dict[str, Any]:
        return {
            "is_hw_v2": self._info.is_hardware_v2,
            "overheated": self._info.overheated,
            "signal_level": self._info.signal_level,
            "auto_off": self._info.auto_off,
            "auto_off_remaining": self._info.auto_off_time_remaining,
            "On since": self.on_since,
            "SSID": self._info.ssid,
        }

    @property
    def features(self) -> Set[str]:
        # TODO:
        return set()
