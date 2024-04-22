"""Implementation of firmware module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from ...exceptions import KasaException, SmartErrorCode
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
    fw_ver: Optional[str] = None  # noqa: UP007
    release_date: Optional[date] = None  # noqa: UP007
    release_notes: Optional[str] = Field(alias="release_note", default=None)  # noqa: UP007
    fw_size: Optional[int] = None  # noqa: UP007
    oem_id: Optional[str] = None  # noqa: UP007
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

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        if self.supported_version > 1:
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
        if device._is_cloud_connected:
            self._add_feature(
                Feature(
                    device,
                    "Update available",
                    container=self,
                    attribute_getter="update_available",
                    type=FeatureType.BinarySensor,
                )
            )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req: dict[str, Any] = {}
        if self._device._is_cloud_connected:
            req["get_latest_fw"] = None

        if self.supported_version > 1:
            req["get_auto_update_info"] = None
        return req

    @property
    def latest_firmware(self):
        """Return latest firmware information."""
        fw = self.data.get("get_latest_fw") or self.data
        if not self._device._is_cloud_connected or isinstance(fw, SmartErrorCode):
            # Error in response, probably disconnected from the cloud.
            return UpdateInfo(type=0, need_to_upgrade=False)

        return UpdateInfo.parse_obj(fw)

    @property
    def update_available(self):
        """Return True if update is available."""
        return self.latest_firmware.update_available

    async def get_update_state(self):
        """Return update state."""
        if self._device._is_cloud_connected:
            return await self.call("get_fw_download_state")
        raise KasaException(
            "Device must be connected to the internet to get firmware download state."
        )

    async def update(self):
        """Update the device firmware."""
        if self._device._is_cloud_connected:
            return await self.call("fw_download")
        raise KasaException(
            "Device must be connected to the internet to download firmware."
        )

    @property
    def auto_update_enabled(self):
        """Return True if autoupdate is enabled."""
        return (
            "get_auto_update_info" in self.data
            and self.data["get_auto_update_info"]["enable"]
        )

    async def set_auto_update_enabled(self, enabled: bool):
        """Change autoupdate setting."""
        data = {**self.data["get_auto_update_info"], "enable": enabled}
        await self.call("set_auto_update_info", data)  # {"enable": enabled})

    async def _check_supported(self) -> bool:
        """Check the module has auto_update or is connected."""
        return self._device._is_cloud_connected or self.supported_version > 1
