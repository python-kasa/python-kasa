"""Implementation of trigger logs module."""

from __future__ import annotations

from datetime import datetime

from pydantic.v1 import BaseModel, Field, parse_obj_as

from ..smartmodule import SmartModule


class LogEntry(BaseModel):
    """Presentation of a single log entry."""

    id: int
    event_id: str = Field(alias="eventId")
    timestamp: datetime
    event: str


class TriggerLogs(SmartModule):
    """Implementation of trigger logs."""

    REQUIRED_COMPONENT = "trigger_log"

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        return {"get_trigger_logs": {"start_id": 0}}

    @property
    def logs(self) -> list[LogEntry]:
        """Return logs."""
        return parse_obj_as(list[LogEntry], self.data["logs"])
