"""The set of plugs a run can drive.

Capped at four from the start. The cap is a UI and sanity limit, not an
architectural one -- the run engine and the event bus are indifferent to how
many sessions exist, which is what makes the planned cross-plug rules a new
subscriber rather than a rewrite.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator, Sequence

from .session import PlugSession

_LOGGER = logging.getLogger(__name__)

#: Concurrent plugs the application supports.
MAX_DEVICES = 4


class RegistryError(Exception):
    """A device could not be added, or was asked for and is not present."""


class DeviceRegistry:
    """Holds the live :class:`PlugSession` objects, keyed by profile id."""

    def __init__(self, *, max_devices: int = MAX_DEVICES) -> None:
        self._sessions: dict[str, PlugSession] = {}
        self._max_devices = max_devices

    def __len__(self) -> int:
        return len(self._sessions)

    def __contains__(self, profile_id: object) -> bool:
        return profile_id in self._sessions

    def __iter__(self) -> Iterator[PlugSession]:
        return iter(self._sessions.values())

    @property
    def sessions(self) -> list[PlugSession]:
        """Every session, in insertion order."""
        return list(self._sessions.values())

    def add(self, session: PlugSession) -> None:
        """Register a session, refusing duplicates and overflow."""
        if session.profile_id in self._sessions:
            raise RegistryError(f"{session.profile_id} is already registered")
        if len(self._sessions) >= self._max_devices:
            raise RegistryError(
                f"at most {self._max_devices} plugs can be driven at once"
            )
        self._sessions[session.profile_id] = session

    def get(self, profile_id: str) -> PlugSession:
        """Look up one session, or raise if it is not registered."""
        try:
            return self._sessions[profile_id]
        except KeyError:
            raise RegistryError(f"no such device: {profile_id}") from None

    def select(self, profile_ids: Sequence[str]) -> list[PlugSession]:
        """Look up several sessions, preserving the order asked for."""
        return [self.get(pid) for pid in profile_ids]

    async def connect_all(self) -> None:
        """Connect every session concurrently, failing if any does not.

        On partial failure the sessions that did connect are torn down, so a
        failed start never leaves half-open connections behind.
        """
        results = await asyncio.gather(
            *(s.connect() for s in self._sessions.values()),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, BaseException)]
        if errors:
            await self.disconnect_all()
            raise RegistryError(
                "could not connect: " + "; ".join(str(e) for e in errors)
            )

    async def disconnect_all(self) -> None:
        """Tear down every session. Never raises."""
        await asyncio.gather(
            *(s.disconnect() for s in self._sessions.values()),
            return_exceptions=True,
        )

    def clear(self) -> None:
        """Forget all sessions. Call only after :meth:`disconnect_all`."""
        self._sessions.clear()
