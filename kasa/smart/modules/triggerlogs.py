"""Implementation of trigger logs module."""

from __future__ import annotations

from dataclasses import dataclass, field

from mashumaro import DataClassDictMixin, field_options

from ..smartmodule import SmartModule


@dataclass
class LogEntry(DataClassDictMixin):
    """Presentation of a single log entry."""

    id: int
    event_id: str = field(metadata=field_options(alias="eventId"))
    timestamp: int
    event: str


class TriggerLogs(SmartModule):
    """Implementation of trigger logs."""

    REQUIRED_COMPONENT = "trigger_log"
    MINIMUM_UPDATE_INTERVAL_SECS = 60 * 60

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"get_trigger_logs": {"start_id": 0}}

    @property
    def logs(self) -> list[LogEntry]:
        """Return logs."""
        return [LogEntry.from_dict(log) for log in self.data["logs"]]
