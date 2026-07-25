"""Implementation of lock module for TP-Link DL100 smart locks."""

from __future__ import annotations

import logging

from ...feature import Feature
from ..smartmodule import SmartModule

_LOGGER = logging.getLogger(__name__)

# lock_status polarity is device-verified and counterintuitive:
#   0 == bolt extended  == LOCKED
#   1 == bolt retracted == UNLOCKED
#   2 UNINITIALIZED, 3 JAM_IN_UNLOCKING, 4 JAM_IN_LOCKING
LOCK_STATUS_LOCKED = 0
LOCK_STATUS_UNLOCKED = 1


class Lock(SmartModule):
    """Implementation of lock module for SMART.TAPOLOCK devices (DL100)."""

    # No component list is exposed by the DL100; depend on the sysinfo key.
    REQUIRED_COMPONENT = None
    SYSINFO_LOOKUP_KEYS = ["lock_status"]

    # Owner (local) path always uses this synthetic user id. Do NOT send
    # tplink_account / access_info / lock_type / unlock_type for the owner.
    SA_USER_ID = "local_1"

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        self._add_feature(
            Feature(
                self._device,
                id="is_locked",
                name="Locked",
                container=self,
                attribute_getter="is_locked",
                icon="mdi:lock",
                category=Feature.Category.Primary,
                type=Feature.Type.BinarySensor,
            )
        )
        # The DL100 reports battery in getDeviceInfo but does NOT advertise the
        # "battery_detect" component, so the generic BatterySensor module never
        # loads for it. Expose battery here instead, mirroring BatterySensor's
        # feature ids so downstream consumers (e.g. Home Assistant) stay
        # consistent.
        if "battery_percentage" in self._device.sys_info:
            self._add_feature(
                Feature(
                    self._device,
                    id="battery_level",
                    name="Battery level",
                    container=self,
                    attribute_getter="battery",
                    icon="mdi:battery",
                    unit_getter=lambda: "%",
                    category=Feature.Category.Info,
                    type=Feature.Type.Sensor,
                )
            )
        if "at_low_battery" in self._device.sys_info:
            self._add_feature(
                Feature(
                    self._device,
                    id="battery_low",
                    name="Battery low",
                    container=self,
                    attribute_getter="battery_low",
                    icon="mdi:alert",
                    category=Feature.Category.Debug,
                    type=Feature.Type.BinarySensor,
                )
            )

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {}

    @property
    def is_locked(self) -> bool:
        """Return True when the bolt is extended (lock_status == 0)."""
        return self._device.sys_info["lock_status"] == LOCK_STATUS_LOCKED

    @property
    def battery(self) -> int:
        """Return the battery level percentage."""
        return self._device.sys_info["battery_percentage"]

    @property
    def battery_low(self) -> bool:
        """Return True if the battery is low."""
        return bool(self._device.sys_info["at_low_battery"])

    async def lock(self) -> dict:
        """Lock the device (extend the bolt)."""
        return await self._set_lock_status(LOCK_STATUS_LOCKED)

    async def unlock(self) -> dict:
        """Unlock the device (retract the bolt)."""
        return await self._set_lock_status(LOCK_STATUS_UNLOCKED)

    async def _set_lock_status(self, status: int) -> dict:
        """Send setLockStatus for the owner (local) path.

        SmartProtocol wraps this into the multipleRequest envelope the device
        expects, so we only supply the method name and params here.
        """
        return await self.call(
            "setLockStatus",
            {"lock_status": status, "sa_user_id": self.SA_USER_ID},
        )
