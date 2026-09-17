"""Request and response bodies.

Validation lives here so a bad number from the browser is rejected with a 422
before it can reach :class:`~gzplug.core.runner.RunPlan`, whose own checks are
the last line of defence rather than the first.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core.registry import MAX_DEVICES


class CredentialsIn(BaseModel):
    """Shared test-team account."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class DiscoverIn(BaseModel):
    """Broadcast discovery parameters."""

    target: str = "255.255.255.255"
    timeout: int = Field(default=5, ge=1, le=60)
    save: bool = True


class AddDeviceIn(BaseModel):
    """Add one plug by address, bypassing broadcast."""

    host: str = Field(min_length=1)
    label: str = ""
    timeout: int = Field(default=5, ge=1, le=60)


class SwitchIn(BaseModel):
    """Manual relay control outside a run."""

    on: bool


class RunIn(BaseModel):
    """Everything the operator sets before pressing Start."""

    devices: list[str] = Field(min_length=1, max_length=MAX_DEVICES)
    cycles: int = Field(ge=1, le=100_000)
    on_time_s: float = Field(ge=0, le=86_400)
    off_time_s: float = Field(ge=0, le=86_400)
    continue_on_error: bool = False
    restore_state: bool = True
    label: str = ""
