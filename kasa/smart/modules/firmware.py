"""Implementation of firmware module."""
from typing import TYPE_CHECKING, Dict, Optional

from ...exceptions import SmartErrorCode
from ...feature import Feature, FeatureType
from ..smartmodule import SmartModule

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
    fw_ver: Optional[str] = None
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

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {"get_auto_update_info": None, "get_latest_fw": None}

    @property
    def latest_firmware(self):
        """Return latest firmware information."""
        fw = self.data["get_latest_fw"]
        if isinstance(fw, SmartErrorCode):
            # Error in response, probably disconnected from the cloud.
            return UpdateInfo(type=0, need_to_upgrade=False)

        return UpdateInfo.parse_obj(fw)

    @property
    def update_available(self):
        """Return True if update is available."""
        return self.latest_firmware.update_available

    async def get_update_state(self):
        """Return update state."""
        return await self.call("get_fw_download_state")

    async def update(self):
        """Update the device firmware."""
        return await self.call("fw_download")

    @property
    def auto_update_enabled(self):
        """Return True if autoupdate is enabled."""
        return self.data["get_auto_update_info"]["enable"]

    async def set_auto_update_enabled(self, enabled: bool):
        """Change autoupdate setting."""
        await self.call("set_auto_update_info", {"enable": enabled})
