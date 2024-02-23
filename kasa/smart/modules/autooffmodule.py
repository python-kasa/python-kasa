"""Implementation of auto off module."""
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, Optional

from ...feature import Feature
from ..smartmodule import SmartModule

if TYPE_CHECKING:
    from ..smartdevice import SmartDevice


class AutoOffModule(SmartModule):
    """Implementation of auto off module."""

    REQUIRED_COMPONENT = "auto_off"
    QUERY_GETTER_NAME = "get_auto_off_config"

    def __init__(self, device: "SmartDevice", module: str):
        super().__init__(device, module)
        self._add_feature(
            Feature(
                device,
                "Auto off enabled",
                container=self,
                attribute_getter="enabled",
                attribute_setter="set_enabled",
            )
        )
        self._add_feature(
            Feature(
                device,
                "Auto off minutes",
                container=self,
                attribute_getter="delay",
                attribute_setter="set_delay",
            )
        )
        self._add_feature(
            Feature(
                device, "Auto off at", container=self, attribute_getter="auto_off_at"
            )
        )

    def query(self) -> Dict:
        """Query to execute during the update cycle."""
        return {self.QUERY_GETTER_NAME: {"start_index": 0}}

    @property
    def enabled(self) -> bool:
        """Return True if enabled."""
        return self.data["enable"]

    def set_enabled(self, enable: bool):
        """Enable/disable auto off."""
        return self.call(
            "set_auto_off_config",
            {"enable": enable, "delay_min": self.data["delay_min"]},
        )

    @property
    def delay(self) -> int:
        """Return time until auto off."""
        return self.data["delay_min"]

    def set_delay(self, delay: int):
        """Set time until auto off."""
        return self.call(
            "set_auto_off_config", {"delay_min": delay, "enable": self.data["enable"]}
        )

    @property
    def is_timer_active(self) -> bool:
        """Return True is auto-off timer is active."""
        return self._device.sys_info["auto_off_status"] == "on"

    @property
    def auto_off_at(self) -> Optional[datetime]:
        """Return when the device will be turned off automatically."""
        if not self.is_timer_active:
            return None

        sysinfo = self._device.sys_info

        return self._device.time + timedelta(seconds=sysinfo["auto_off_remain_time"])
