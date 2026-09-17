"""Periodic sampling of plug state and energy metering.

This is the only reason historical energy data will exist. The KP125M reports
instantaneous power, voltage, current and running today/month totals, but it
keeps no per-hour or per-day history -- so anything the future energy view
plots has to be sampled and written down as the run happens.

A failed poll is recorded but never aborts a run. Polling is observational;
the run engine's own commands are what enforce fail-fast, and the next one
will surface an unreachable device.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime

from .events import Event, EventBus, EventKind, Sample
from .registry import DeviceRegistry
from .session import PlugSession, SessionFault

_LOGGER = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 2.0


class Poller:
    """Samples every connected plug on a fixed interval."""

    def __init__(
        self,
        registry: DeviceRegistry,
        bus: EventBus,
        *,
        interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("poll interval must be positive")
        self._registry = registry
        self._bus = bus
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        """True while the sampling loop is live."""
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Begin sampling in the background."""
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="gzplug-poller")

    async def stop(self) -> None:
        """Stop sampling and wait for the loop to unwind."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self._sample_all()

    async def _sample_all(self) -> None:
        sessions = [s for s in self._registry.sessions if s.connected]
        if not sessions:
            return
        await asyncio.gather(
            *(self._sample_one(s) for s in sessions), return_exceptions=True
        )

    async def _sample_one(self, session: PlugSession) -> None:
        try:
            sample = await session.read()
        except SessionFault as exc:
            # The session has already published a FAULT event with detail;
            # swallowing here keeps a flaky poll from ending a good run.
            _LOGGER.debug("poll failed for %s: %s", session.label, exc)
            return
        self._publish(session, sample)

    def _publish(self, session: PlugSession, sample: Sample) -> None:
        self._bus.publish(
            Event(
                kind=EventKind.SAMPLE,
                timestamp=datetime.now().astimezone(),
                device=session.profile_id,
                sample=sample,
            )
        )
