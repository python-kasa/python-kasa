"""Cloud module implementation."""
try:
    from pydantic.v1 import BaseModel
except ImportError:
    from pydantic import BaseModel

from ...descriptors import Descriptor, DescriptorType
from .module import IotModule


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


class Cloud(IotModule):
    """Module implementing support for cloud services."""

    def __init__(self, device, module):
        super().__init__(device, module)
        self.add_descriptor(
            Descriptor(
                device=self,
                name="Cloud Connection",
                icon="mdi:cloud",
                attribute_getter="is_connected",
                type=DescriptorType.BinarySensor,
            )
        )

    @property
    def is_connected(self) -> bool:
        """Return true if device is connected to the cloud."""
        return self.info.binded

    def query(self):
        """Request cloud connectivity info."""
        return self.query_for_command("get_info")

    @property
    def info(self) -> CloudInfo:
        """Return information about the cloud connectivity."""
        return CloudInfo.parse_obj(self.data["get_info"])

    def get_available_firmwares(self):
        """Return list of available firmwares."""
        return self.query_for_command("get_intl_fw_list")

    def set_server(self, url: str):
        """Set the update server URL."""
        return self.query_for_command("set_server_url", {"server": url})

    def connect(self, username: str, password: str):
        """Login to the cloud using given information."""
        return self.query_for_command(
            "bind", {"username": username, "password": password}
        )

    def disconnect(self):
        """Disconnect from the cloud."""
        return self.query_for_command("unbind")
