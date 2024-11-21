"""Implementation of firmware module."""

from __future__ import annotations

import asyncio
import logging
from asyncio import timeout as asyncio_timeout
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Annotated

from mashumaro import DataClassDictMixin, field_options
from mashumaro.types import Alias

from ...exceptions import KasaException
from ...feature import Feature
from ..smartmodule import SmartModule, allow_update_after

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


_LOGGER = logging.getLogger(__name__)


@dataclass
class DownloadState(DataClassDictMixin):
    """Download state."""

    # Example:
    #   {'status': 0, 'download_progress': 0, 'reboot_time': 5,
    #    'upgrade_time': 5, 'auto_upgrade': False}
    status: int
    progress: Annotated[int, Alias("download_progress")]
    reboot_time: int
    upgrade_time: int
    auto_upgrade: bool


@dataclass
class UpdateInfo(DataClassDictMixin):
    """Update info status object."""

    status: Annotated[int, Alias("type")]
    needs_upgrade: Annotated[bool, Alias("need_to_upgrade")]
    version: Annotated[str | None, Alias("fw_ver")] = None
    release_date: date | None = field(
        default=None,
        metadata=field_options(
            deserialize=lambda x: date.fromisoformat(x) if x else None
        ),
    )
    release_notes: Annotated[str | None, Alias("release_note")] = None
    fw_size: int | None = None
    oem_id: str | None = None

    @property
    def update_available(self) -> bool:
        """Return True if update available."""
        return self.status != 0


class Firmware(SmartModule):
    """Implementation of firmware module."""

    REQUIRED_COMPONENT = "firmware"
    MINIMUM_UPDATE_INTERVAL_SECS = 60 * 60 * 24

    def __init__(self, device: SmartDevice, module: str) -> None:
        super().__init__(device, module)
        self._firmware_update_info: UpdateInfo | None = None

    def _initialize_features(self) -> None:
        """Initialize features."""
        device = self._device
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
                type=Feature.Type.Sensor,
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
                type=Feature.Type.Sensor,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="check_latest_firmware",
                name="Check latest firmware",
                container=self,
                attribute_setter="check_latest_firmware",
                category=Feature.Category.Info,
                type=Feature.Type.Action,
            )
        )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        if self.supported_version > 1:
            return {"get_auto_update_info": None}
        return {}

    async def check_latest_firmware(self) -> UpdateInfo | None:
        """Check for the latest firmware for the device."""
        try:
            fw = await self.call("get_latest_fw")
            self._firmware_update_info = UpdateInfo.from_dict(fw["get_latest_fw"])
            return self._firmware_update_info
        except Exception:
            _LOGGER.exception("Error getting latest firmware for %s:", self._device)
            self._firmware_update_info = None
            return None

    @property
    def current_firmware(self) -> str:
        """Return the current firmware version."""
        return self._device.hw_info["sw_ver"]

    @property
    def latest_firmware(self) -> str | None:
        """Return the latest firmware version."""
        if not self._firmware_update_info:
            return None
        return self._firmware_update_info.version

    @property
    def firmware_update_info(self) -> UpdateInfo | None:
        """Return latest firmware information."""
        return self._firmware_update_info

    @property
    def update_available(self) -> bool | None:
        """Return True if update is available."""
        if not self._device.is_cloud_connected or not self._firmware_update_info:
            return None
        return self._firmware_update_info.update_available

    async def get_update_state(self) -> DownloadState:
        """Return update state."""
        resp = await self.call("get_fw_download_state")
        state = resp["get_fw_download_state"]
        return DownloadState.from_dict(state)

    @allow_update_after
    async def update(
        self, progress_cb: Callable[[DownloadState], Coroutine] | None = None
    ) -> dict:
        """Update the device firmware."""
        if not self._firmware_update_info:
            raise KasaException(
                "You must call check_latest_firmware before calling update"
            )
        if not self.update_available:
            raise KasaException("A new update must be available to call update")
        current_fw = self.current_firmware
        _LOGGER.info(
            "Going to upgrade from %s to %s",
            current_fw,
            self._firmware_update_info.version,
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

                _LOGGER.debug("Update state: %s", state)
                if progress_cb is not None:
                    asyncio.create_task(progress_cb(state))

                if state.status == 0:
                    _LOGGER.info(
                        "Update idle, hopefully updated to %s",
                        self._firmware_update_info.version,
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

        return state.to_dict()

    @property
    def auto_update_enabled(self) -> bool:
        """Return True if autoupdate is enabled."""
        return "enable" in self.data and self.data["enable"]

    @allow_update_after
    async def set_auto_update_enabled(self, enabled: bool) -> dict:
        """Change autoupdate setting."""
        data = {**self.data, "enable": enabled}
        return await self.call("set_auto_update_info", data)
