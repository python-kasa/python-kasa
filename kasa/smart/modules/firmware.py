"""Implementation of firmware module."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout
from pydantic.v1 import BaseModel, Field, validator
# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout

from ...exceptions import SmartErrorCode
from ...feature import Feature, FeatureType
from ...firmware import Firmware as FirmwareInterface
from ...firmware import FirmwareUpdate as FirmwareUpdateInterface
from ...firmware import UpdateResult
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


class FirmwareUpdate(BaseModel):
    """Update info status object."""

    status: int = Field(alias="type")
    version: Optional[str] = Field(alias="fw_ver", default=None)  # noqa: UP007
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


class Firmware(SmartModule, FirmwareInterface):
    """Implementation of firmware module."""

    REQUIRED_COMPONENT = "firmware"

    def __init__(self, device: SmartDevice, module: str):
        super().__init__(device, module)
        if self.supported_version > 1:
            self._add_feature(
                Feature(
                    device,
                    id="auto_update_enabled",
                    name="Auto update enabled",
                    container=self,
                    attribute_getter="auto_update_enabled",
                    attribute_setter="set_auto_update_enabled",
                    type=Feature.Type.Switch,
                )
            )
        self._add_feature(
            Feature(
                device,
                id="update_available",
                name="Update available",
                container=self,
                attribute_getter="update_available",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="current_firmware_version",
                name="Current firmware version",
                container=self,
                attribute_getter="current_firmware",
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="available_firmware_version",
                name="Available firmware version",
                container=self,
                attribute_getter="latest_firmware",
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device,
                "Current firmware version",
                container=self,
                attribute_getter="current_firmware",
            )
        )
        self._add_feature(
            Feature(
                device,
                "Available firmware version",
                container=self,
                attribute_getter="latest_firmware",
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req: dict[str, Any] = {"get_latest_fw": None}
        if self.supported_version > 1:
            req["get_auto_update_info"] = None
        return req

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
        fw = self.data.get("get_latest_fw") or self.data
        if not self._device.is_cloud_connected or isinstance(fw, SmartErrorCode):
            # Error in response, probably disconnected from the cloud.
            return FirmwareUpdate(type=0, need_to_upgrade=False)

        return FirmwareUpdate.parse_obj(fw)

    @property
    def update_available(self) -> bool | None:
        """Return True if update is available."""
        if not self._device.is_cloud_connected:
            return None
        return self.firmware_update_info.update_available

    async def get_update_state(self):
        """Return update state."""
        return await self.call("get_fw_download_state")

    async def update(self):
        """Update the device firmware."""
        current_fw = self.current_firmware
        _LOGGER.debug(
            "Going to upgrade from %s to %s",
            current_fw,
            self.firmware_update_info.version,
        )
        resp = await self.call("fw_download")
        _LOGGER.debug("Update request response: %s", resp)
        # TODO: read timeout from get_auto_update_info or from get_fw_download_state?
        async with asyncio_timeout(60 * 5):
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
        return (
            "get_auto_update_info" in self.data
            and self.data["get_auto_update_info"]["enable"]
        )

    async def set_auto_update_enabled(self, enabled: bool):
        """Change autoupdate setting."""
        data = {**self.data["get_auto_update_info"], "enable": enabled}
        await self.call("set_auto_update_info", data)

    async def update_firmware(self, *, progress_cb) -> UpdateResult:
        """Update the firmware."""
        # TODO: implement, this is part of the common firmware API
        raise NotImplementedError

    async def check_for_updates(self) -> FirmwareUpdateInterface:
        """Return firmware update information."""
        # TODO: naming of the common firmware API methods
        info = self.firmware_update_info
        return FirmwareUpdateInterface(
            current_version=self.current_firmware,
            update_available=info.update_available,
            available_version=info.version,
            release_date=info.release_date,
            release_notes=info.release_notes,
        )
