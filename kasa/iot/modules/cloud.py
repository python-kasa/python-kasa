"""Cloud module implementation."""

from dataclasses import dataclass
from typing import Annotated

from mashumaro import DataClassDictMixin
from mashumaro.types import Alias

from ...feature import Feature
from ..iotmodule import IotModule


@dataclass
class CloudInfo(DataClassDictMixin):
    """Container for cloud settings."""

    provisioned: Annotated[int, Alias("binded")]
    cloud_connected: Annotated[int, Alias("cld_connection")]
    firmware_download_page: Annotated[str, Alias("fwDlPage")]
    firmware_notify_type: Annotated[int, Alias("fwNotifyType")]
    illegal_type: Annotated[int, Alias("illegalType")]
    server: str
    stop_connect: Annotated[int, Alias("stopConnect")]
    tcsp_info: Annotated[str, Alias("tcspInfo")]
    tcsp_status: Annotated[int, Alias("tcspStatus")]
    username: str


class Cloud(IotModule):
    """Module implementing support for cloud services."""

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                device=self._device,
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
        return bool(self.info.cloud_connected)

    def query(self) -> dict:
        """Request cloud connectivity info."""
        return self.query_for_command("get_info")

    @property
    def info(self) -> CloudInfo:
        """Return information about the cloud connectivity."""
        return CloudInfo.from_dict(self.data["get_info"])

    def get_available_firmwares(self) -> dict:
        """Return list of available firmwares."""
        return self.query_for_command("get_intl_fw_list")

    def set_server(self, url: str) -> dict:
        """Set the update server URL."""
        return self.query_for_command("set_server_url", {"server": url})

    def connect(self, username: str, password: str) -> dict:
        """Login to the cloud using given information."""
        return self.query_for_command(
            "bind", {"username": username, "password": password}
        )

    def disconnect(self) -> dict:
        """Disconnect from the cloud."""
        return self.query_for_command("unbind")
