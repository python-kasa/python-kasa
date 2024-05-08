"""Implementation of firmware module."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

# When support for cpython older than 3.11 is dropped
# async_timeout can be replaced with asyncio.timeout
from async_timeout import timeout as asyncio_timeout
from pydantic.v1 import BaseModel, Field, validator

from ...exceptions import SmartErrorCode
from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


class DownloadState(BaseModel):
    """Download state."""

    # Example:
    #   {'status': 0, 'download_progress': 0, 'reboot_time': 5,
    #    'upgrade_time': 5, 'auto_upgrade': False}
    status: int
    progress: int = Field(alias="download_progress")
    reboot_time: int
    upgrade_time: int
    auto_upgrade: bool


class UpdateInfo(BaseModel):
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


class Firmware(SmartModule):
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
                category=Feature.Category.Debug,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="available_firmware_version",
                name="Available firmware version",
                container=self,
                attribute_getter="latest_firmware",
                category=Feature.Category.Debug,
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
            return UpdateInfo(type=0, need_to_upgrade=False)

        return UpdateInfo.parse_obj(fw)

    @property
    def update_available(self) -> bool | None:
        """Return True if update is available."""
        if not self._device.is_cloud_connected:
            return None
        return self.firmware_update_info.update_available

    async def get_update_state(self) -> DownloadState:
        """Return update state."""
        resp = await self.call("get_fw_download_state")
        state = resp["get_fw_download_state"]
        return DownloadState(**state)

    async def update(
        self, progress_cb: Callable[[DownloadState], Coroutine] | None = None
    ):
        """Update the device firmware."""
        current_fw = self.current_firmware
        _LOGGER.info(
            "Going to upgrade from %s to %s",
            current_fw,
            self.firmware_update_info.version,
        )
        await self.call("fw_download")

        # TODO: read timeout from get_auto_update_info or from get_fw_download_state?
        async with asyncio_timeout(60 * 5):
            while True:
                await asyncio.sleep(0.5)
                try:
                    state = await self.get_update_state()
                except Exception as ex:
                    _LOGGER.warning(
                        "Got exception, maybe the device is rebooting? %s", ex
                    )
                    continue

                _LOGGER.debug("Update state: %s" % state)
                if progress_cb is not None:
                    asyncio.create_task(progress_cb(state))

                if state.status == 0:
                    _LOGGER.info(
                        "Update idle, hopefully updated to %s",
                        self.firmware_update_info.version,
                    )
                    break
                elif state.status == 2:
                    _LOGGER.info("Downloading firmware, progress: %s", state.progress)
                elif state.status == 3:
                    upgrade_sleep = state.upgrade_time
                    _LOGGER.info(
                        "Flashing firmware, sleeping for %s before checking status",
                        upgrade_sleep,
                    )
                    await asyncio.sleep(upgrade_sleep)
                elif state.status < 0:
                    _LOGGER.error("Got error: %s", state.status)
                    break
                else:
                    _LOGGER.warning("Unhandled state code: %s", state)

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
