"""Implementation of lock history module for door locks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ...feature import Feature
from ...interfaces.lock import LockEvent, LockMethod
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


@dataclass
class LockLogEntry:
    """Lock log entry."""

    timestamp: datetime
    event_type: LockEvent
    method: LockMethod
    user: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> LockLogEntry:
        """Create LockLogEntry from dict."""
        timestamp = datetime.fromtimestamp(data.get("timestamp", 0))
        event_type = LockEvent(data.get("event_type", "unknown").lower())
        method = LockMethod.from_value(data.get("method", "unknown"))
        user = data.get("user")
        return cls(timestamp=timestamp, event_type=event_type, method=method, user=user)


class LockHistory(SmartCamModule):
    """Implementation of lock history module for door locks."""

    REQUIRED_COMPONENT = "lock"
    QUERY_GETTER_NAME = "getLockLogs"
    QUERY_MODULE_NAME = "lock"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        q = super().query()
        q["getLockLogCount"] = {self.QUERY_MODULE_NAME: {}}
        return q

    def _initialize_features(self) -> None:
        """Initialize features."""
        device = self._device
        self._add_feature(
            Feature(
                device,
                id="lock_total_logs",
                name="Lock total logs",
                container=self,
                attribute_getter="total_log_count",
                icon="mdi:history",
                category=Feature.Category.Debug,
                type=Feature.Type.Sensor,
            )
        )

    def _get_lock_logs_data(self) -> dict:
        """Get lock logs data."""
        return self.data.get(self.QUERY_GETTER_NAME, {})

    def _get_lock_log_count_data(self) -> dict:
        """Get lock log count data."""
        return self.data.get("getLockLogCount", {})

    @property
    def total_log_count(self) -> int:
        """Return total number of lock logs."""
        count_data = self._get_lock_log_count_data()
        return count_data.get("total_count", 0)

    @property
    def logs(self) -> list[LockLogEntry]:
        """Return list of lock log entries."""
        logs_data = self._get_lock_logs_data()
        log_list = logs_data.get("log_list", [])
        return [LockLogEntry.from_dict(entry) for entry in log_list]

    @property
    def recent_locks(self) -> list[LockLogEntry]:
        """Return recent lock entries."""
        return [log for log in self.logs if log.event_type == LockEvent.Lock]

    @property
    def recent_unlocks(self) -> list[LockLogEntry]:
        """Return recent unlock entries."""
        return [log for log in self.logs if log.event_type == LockEvent.Unlock]

    @property
    def last_lock(self) -> LockLogEntry | None:
        """Return the most recent lock entry."""
        locks = self.recent_locks
        return locks[0] if locks else None

    @property
    def last_unlock(self) -> LockLogEntry | None:
        """Return the most recent unlock entry."""
        unlocks = self.recent_unlocks
        return unlocks[0] if unlocks else None
