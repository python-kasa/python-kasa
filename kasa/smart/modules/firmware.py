"""Implementation of firmware module."""
from typing import TYPE_CHECKING, Dict, Optional
import asyncio

from ...exceptions import SmartErrorCode
from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout


try:
    from pydantic.v1 import BaseModel, Field, validator
except ImportError:
    from pydantic import BaseModel, Field, validator
from datetime import date

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class UpdateInfo(BaseModel):
    """Update info status object."""

    status: int = Field(alias="type")
    version: Optional[str] = Field(alias="fw_ver", default=None)
    release_date: Optional[date] = None
    release_notes: Optional[str] = Field(alias="release_note", default=None)
    fw_size: Optional[int] = None
    oem_id: Optional[str] = None
    needs_upgrade: bool = Field(alias="need_to_upgrade")

    @validator("release_date", pre=True)
    def _release_date_optional(cls, v):
        if not v:
            return None

        return v

    @property
    def update_available(self):
        """Return True if update available."""
        if self.status != 0:
            return True
        return False


class Firmware(SmartModule):
    """Implementation of firmware module."""

    REQUIRED_COMPONENT = "firmware"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Auto update enabled",
                container=self,
                attribute_getter="auto_update_enabled",
                attribute_setter="set_auto_update_enabled",
                type=FeatureType.Switch,
            )
        )
        self._add_feature(
            Feature(
                device,
                "Update available",
                container=self,
                attribute_getter="update_available",
                type=FeatureType.BinarySensor,
            )
        )
        self._add_feature(
            Feature(device, "Current firmware version", container=self, attribute_getter="current_firmware")
        )
        self._add_feature(
            Feature(device, "Available firmware version", container=self, attribute_getter="latest_firmware")
        )

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {"get_auto_update_info": None, "get_latest_fw": None}

    @property
    def current_firmware(self) -> str:
        """Return the current firmware version."""
        return self._device.hw_info["sw_ver"]


    @property
    def latest_firmware(self) -> str:
        """Return the latest firmware version."""
        return self.firmware_update_info.version

    @property
    def firmware_update_info(self):
        """Return latest firmware information."""
        fw = self.data["get_latest_fw"]
        if isinstance(fw, SmartErrorCode):
            # Error in response, probably disconnected from the cloud.
            return UpdateInfo(type=0, need_to_upgrade=False)

        return UpdateInfo.parse_obj(fw)

    @property
    def update_available(self):
        """Return True if update is available."""
        return self.firmware_update_info.update_available

    async def get_update_state(self):
        """Return update state."""
        return await self.call("get_fw_download_state")

    async def update(self):
        """Update the device firmware."""
        current_fw = self.current_firmware
        _LOGGER.debug("Going to upgrade from %s to %s", current_fw, self.firmware_update_info.version)
        resp = await self.call("fw_download")
        _LOGGER.debug("Update request response: %s", resp)
        # TODO: read timeout from get_auto_update_info or from get_fw_download_state?
        async with asyncio_timeout(60*5):
            while True:
                await asyncio.sleep(0.5)
                state = await self.get_update_state()
                _LOGGER.debug("Update state: %s" % state)
                # TODO: this could await a given callable for progress

                if self.firmware_update_info.version != current_fw:
                    _LOGGER.info("Updated to %s", self.firmware_update_info.version)
                    break

    @property
    def auto_update_enabled(self):
        """Return True if autoupdate is enabled."""
        return self.data["get_auto_update_info"]["enable"]

    async def set_auto_update_enabled(self, enabled: bool):
        """Change autoupdate setting."""
        data = {**self.data["get_auto_update_info"], "enable": enabled}
        await self.call("set_auto_update_info", data)
