"""Cloud module implementation."""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Coroutine, Optional

from pydantic.v1 import BaseModel, Field, validator

from ...feature import Feature
from ...interfaces.firmware import (
    Firmware,
    UpdateResult,
)
from ...interfaces.firmware import (
    FirmwareDownloadState as FirmwareDownloadStateInterface,
)
from ...interfaces.firmware import (
    FirmwareUpdateInfo as FirmwareUpdateInfoInterface,
)
from ..iotmodule import IotModule

_LOGGER = logging.getLogger(__name__)


class CloudInfo(BaseModel):
    """Container for cloud settings."""

    binded: bool
    cld_connection: int
    fwDlPage: str
    fwNotifyType: int
    illegalType: int
    server: str
    stopConnect: int
    tcspInfo: str
    tcspStatus: int
    username: str


class FirmwareUpdate(BaseModel):
    """Update info status object."""

    status: int = Field(alias="fwType")
    version: Optional[str] = Field(alias="fwVer", default=None)  # noqa: UP007
    release_date: Optional[date] = Field(alias="fwReleaseDate", default=None)  # noqa: UP007
    release_notes: Optional[str] = Field(alias="fwReleaseLog", default=None)  # noqa: UP007
    url: Optional[str] = Field(alias="fwUrl", default=None)  # noqa: UP007

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


class Cloud(IotModule, Firmware):
    """Module implementing support for cloud services."""

    def __init__(self, device, module):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device=device,
                container=self,
                id="cloud_connection",
                name="Cloud connection",
                icon="mdi:cloud",
                attribute_getter="is_connected",
                type=Feature.Type.BinarySensor,
                category=Feature.Category.Info,
            )
        )

    @property
    def is_connected(self) -> bool:
        """Return true if device is connected to the cloud."""
        return self.info.binded

    def query(self):
        """Request cloud connectivity info."""
        req = self.query_for_command("get_info")

        # TODO: this is problematic, as it will fail the whole query on some
        #  devices if they are not connected to the internet

        # The following causes a recursion error as self.is_connected
        # accesses self.data which calls query.  Also get_available_firmwares is async
        # if self._module in self._device._last_update and self.is_connected:
        #    req = merge(req, self.get_available_firmwares())

        return req

    @property
    def info(self) -> CloudInfo:
        """Return information about the cloud connectivity."""
        return CloudInfo.parse_obj(self.data["get_info"])

    async def get_available_firmwares(self):
        """Return list of available firmwares."""
        return await self.call("get_intl_fw_list")

    async def get_firmware_update(self) -> FirmwareUpdate:
        """Return firmware update information."""
        try:
            available_fws = (await self.get_available_firmwares()).get("fw_list", [])
            if not available_fws:
                return FirmwareUpdate(fwType=0)
            if len(available_fws) > 1:
                _LOGGER.warning(
                    "Got more than one update, using the first one: %s", available_fws
                )
            return FirmwareUpdate.parse_obj(next(iter(available_fws)))
        except Exception as ex:
            _LOGGER.warning("Unable to check for firmware update: %s", ex)
            return FirmwareUpdate(fwType=0)

    async def set_server(self, url: str):
        """Set the update server URL."""
        return await self.call("set_server_url", {"server": url})

    async def connect(self, username: str, password: str):
        """Login to the cloud using given information."""
        return await self.call("bind", {"username": username, "password": password})

    async def disconnect(self):
        """Disconnect from the cloud."""
        return await self.call("unbind")

    async def update_firmware(
        self,
        *,
        progress_cb: Callable[[FirmwareDownloadStateInterface], Coroutine]
        | None = None,
    ) -> UpdateResult:
        """Perform firmware update."""
        raise NotImplementedError
        i = 0
        import asyncio

        while i < 100:
            await asyncio.sleep(1)
            if progress_cb is not None:
                await progress_cb(i)
            i += 10

        return UpdateResult("")

    async def check_for_updates(self) -> FirmwareUpdateInfoInterface:
        """Return firmware update information."""
        # TODO: naming of the common firmware API methods
        raise NotImplementedError

    async def get_update_state(self) -> FirmwareUpdateInfoInterface:
        """Return firmware update information."""
        fw = await self.get_firmware_update()

        return FirmwareUpdateInfoInterface(
            update_available=fw.update_available,
            current_version=self._device.hw_info.get("sw_ver"),
            available_version=fw.version,
            release_date=fw.release_date,
            release_notes=fw.release_notes,
        )
