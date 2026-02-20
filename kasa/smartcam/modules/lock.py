"""Implementation of lock module for door locks."""

from __future__ import annotations

import logging
from datetime import datetime

from ...feature import Feature
from ...interfaces.lock import Lock as LockInterface
from ...interfaces.lock import LockMethod
from ...smart.smartmodule import allow_update_after
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class Lock(SmartCamModule, LockInterface):
    """Implementation of lock module for door locks."""

    REQUIRED_COMPONENT = "lock"
    QUERY_GETTER_NAME = "getLockStatus"
    QUERY_MODULE_NAME = "lock"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        q["getLockConfig"] = {self.QUERY_MODULE_NAME: {}}
        return q

    def _initialize_features(self) -> None:
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="lock",
                name="Lock",
                container=self,
                attribute_getter="is_locked",
                attribute_setter="set_locked",
                icon="mdi:lock",
                category=Feature.Category.Config,
                type=Feature.Type.Switch,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="auto_lock_enabled",
                name="Auto lock",
                container=self,
                attribute_getter="auto_lock_enabled",
                attribute_setter="set_auto_lock_enabled",
                icon="mdi:lock-clock",
                category=Feature.Category.Config,
                type=Feature.Type.Switch,
            )
        )
        self._add_feature(
            Feature(
                device,
                id="auto_lock_time",
                name="Auto lock time",
                container=self,
                attribute_getter="auto_lock_time",
                attribute_setter="set_auto_lock_time",
                icon="mdi:timer",
                unit_getter=lambda: "s",
                category=Feature.Category.Config,
                type=Feature.Type.Number,
            )
        )

    def _get_lock_status(self) -> dict:
        """Get lock status data."""
        return self.data.get(self.QUERY_GETTER_NAME, {})

    def _get_lock_config(self) -> dict:
        """Get lock config data."""
        return self.data.get("getLockConfig", {})

    @property
    def is_locked(self) -> bool:
        """Return True if the device is locked."""
        status = self._get_lock_status()
        return status.get("lock_status", "").lower() == "locked"

    @property
    def battery_level(self) -> int | None:
        """Return battery level percentage or None if not available."""
        status = self._get_lock_status()
        battery = status.get("battery_percent")
        return int(battery) if battery is not None else None

    @property
    def auto_lock_enabled(self) -> bool:
        """Return True if auto-lock is enabled."""
        config = self._get_lock_config()
        return config.get("auto_lock_enabled", False)

    @property
    def auto_lock_time(self) -> int | None:
        """Return auto-lock time in seconds or None if not available."""
        config = self._get_lock_config()
        return config.get("auto_lock_time")

    @property
    def last_unlock_method(self) -> LockMethod:
        """Return the method used to unlock the door last time."""
        status = self._get_lock_status()
        method = status.get("last_unlock_method", "unknown")
        return LockMethod.from_value(method)

    @property
    def last_unlock_user(self) -> str | None:
        """Return the user who last unlocked the door."""
        status = self._get_lock_status()
        return status.get("last_unlock_user")

    @property
    def last_unlock_time(self) -> datetime | None:
        """Return the time of the last unlock as a datetime object."""
        status = self._get_lock_status()
        timestamp = status.get("last_unlock_time")
        if timestamp is not None:
            return datetime.fromtimestamp(timestamp)
        return None

    @allow_update_after
    async def lock(self) -> None:
        """Lock the device."""
        await self.call("setLockStatus", {"lock": {"lock_status": "locked"}})

    @allow_update_after
    async def unlock(self) -> None:
        """Unlock the device."""
        await self.call("setLockStatus", {"lock": {"lock_status": "unlocked"}})

    @allow_update_after
    async def set_locked(self, locked: bool) -> None:
        """Set the lock status."""
        if locked:
            await self.lock()
        else:
            await self.unlock()

    @allow_update_after
    async def set_auto_lock_enabled(self, enabled: bool) -> None:
        """Set auto-lock enabled."""
        config = self._get_lock_config()
        params = dict(config)
        params["auto_lock_enabled"] = enabled
        await self.call("setLockConfig", {"lock": params})

    @allow_update_after
    async def set_auto_lock_time(self, time_seconds: int) -> None:
        """Set auto-lock time in seconds."""
        config = self._get_lock_config()
        params = dict(config)
        params["auto_lock_time"] = time_seconds
        await self.call("setLockConfig", {"lock": params})
