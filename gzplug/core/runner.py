"""Executes a cycle plan across one to four plugs.

The engine drives plugs and emits events. It does not log, render, or decide
anything about cross-plug behaviour -- those are subscribers on the bus. That
separation is what keeps the planned interdependence feature additive.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from .events import Event, EventBus, EventKind, Phase, Result
from .registry import DeviceRegistry
from .session import PlugSession

_LOGGER = logging.getLogger(__name__)


class RunState(StrEnum):
    """Where a run is in its life."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class RunFailed(Exception):
    """A run stopped because a device operation failed."""


@dataclass(frozen=True, slots=True)
class RunPlan:
    """What a run should do.

    :param continue_on_error: retry and press on through faults instead of
        stopping at the first one. Off by default, so an anomaly surfaces
        rather than producing a clean-looking log of a test that did not
        happen.
    :param restore_state: put each plug back to the state it was found in
        when the run ends, including on abort.
    """

    devices: tuple[str, ...]
    cycles: int
    on_time_s: float
    off_time_s: float
    continue_on_error: bool = False
    restore_state: bool = True
    label: str = ""

    def __post_init__(self) -> None:
        """Reject plans that cannot be executed."""
        if not self.devices:
            raise ValueError("a run needs at least one device")
        if len(set(self.devices)) != len(self.devices):
            raise ValueError("the same device is listed more than once")
        if self.cycles < 1:
            raise ValueError("a run needs at least one cycle")
        if self.on_time_s < 0 or self.off_time_s < 0:
            raise ValueError("on/off times cannot be negative")


@dataclass
class RunStatus:
    """Live progress, for the UI and for tests."""

    state: RunState = RunState.IDLE
    plan: RunPlan | None = None
    cycle: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    faults: dict[str, int] = field(default_factory=dict)


class RunEngine:
    """Runs one :class:`RunPlan` at a time against the registry."""

    def __init__(self, registry: DeviceRegistry, bus: EventBus) -> None:
        self._registry = registry
        self._bus = bus
        self._status = RunStatus()
        self._task: asyncio.Task[None] | None = None

    @property
    def status(self) -> RunStatus:
        """Current progress snapshot."""
        return self._status

    @property
    def running(self) -> bool:
        """True while a run is in flight."""
        return self._status.state is RunState.RUNNING

    # -- control -------------------------------------------------------

    def start(self, plan: RunPlan) -> asyncio.Task[None]:
        """Launch *plan* in the background and return its task."""
        if self.running:
            raise RunFailed("a run is already in progress")
        self._task = asyncio.create_task(self.execute(plan), name="gzplug-run")
        return self._task

    async def stop(self) -> None:
        """Ask the current run to stop, and wait for it to tidy up.

        The plugs are still restored, because the engine catches the
        cancellation and runs its restore step before returning.
        """
        task, self._task = self._task, None
        if task is None or task.done():
            return
        task.cancel()
        # A deliberate stop is not an error here.
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def execute(self, plan: RunPlan) -> None:
        """Run *plan* to completion. Raises :class:`RunFailed` on fault."""
        sessions = self._registry.select(plan.devices)
        self._status = RunStatus(
            state=RunState.RUNNING,
            plan=plan,
            started_at=datetime.now().astimezone(),
        )
        self._publish(
            EventKind.RUN_STARTED,
            detail=(
                f"{plan.cycles} cycle(s), {plan.on_time_s}s on / "
                f"{plan.off_time_s}s off, {len(sessions)} device(s)"
                + (", continue-on-error" if plan.continue_on_error else "")
            ),
        )

        outcome = RunState.COMPLETED
        error: Exception | None = None
        try:
            await self._run_cycles(sessions, plan)
        except asyncio.CancelledError:
            # A deliberate stop. Swallowed here so the restore below is not
            # unwinding through a cancellation, and so stop() returns cleanly.
            outcome = RunState.ABORTED
        except RunFailed as exc:
            outcome, error = RunState.FAILED, exc

        if plan.restore_state:
            await self._restore(sessions)

        self._status.state = outcome
        self._status.finished_at = datetime.now().astimezone()
        self._status.error = str(error) if error else None
        self._status.faults = {s.profile_id: s.fault_count for s in sessions}
        self._publish(
            EventKind.RUN_FINISHED,
            result=Result.OK if outcome is RunState.COMPLETED else Result.ERROR,
            detail=f"{outcome.value}"
            + (f": {error}" if error else "")
            + f" (faults: {sum(self._status.faults.values())})",
        )

        if error is not None:
            raise error

    # -- internals -----------------------------------------------------

    async def _run_cycles(self, sessions: list[PlugSession], plan: RunPlan) -> None:
        for cycle in range(1, plan.cycles + 1):
            self._status.cycle = cycle
            self._publish(
                EventKind.CYCLE_STARTED,
                cycle=cycle,
                detail=f"cycle {cycle} of {plan.cycles}",
            )
            await self._step(sessions, on=True, cycle=cycle, plan=plan)
            await asyncio.sleep(plan.on_time_s)
            await self._step(sessions, on=False, cycle=cycle, plan=plan)
            await asyncio.sleep(plan.off_time_s)

    async def _step(
        self,
        sessions: list[PlugSession],
        *,
        on: bool,
        cycle: int,
        plan: RunPlan,
    ) -> None:
        """Switch every plug together, then decide whether to keep going."""
        phase = Phase.ON if on else Phase.OFF
        results = await asyncio.gather(
            *(s.set_state(on, cycle=cycle, phase=phase) for s in sessions),
            return_exceptions=True,
        )
        failures = [
            (session, result)
            for session, result in zip(sessions, results, strict=True)
            if isinstance(result, BaseException)
        ]
        if not failures:
            return

        # Cancellation is not a device fault; let it unwind the run.
        for _, result in failures:
            if isinstance(result, asyncio.CancelledError):
                raise result

        summary = "; ".join(f"{s.label}: {exc}" for s, exc in failures)
        if not plan.continue_on_error:
            raise RunFailed(f"cycle {cycle} {phase.value}: {summary}")
        _LOGGER.warning("continuing past fault in cycle %s: %s", cycle, summary)

    async def _restore(self, sessions: list[PlugSession]) -> None:
        """Put the plugs back, and say so loudly if one refuses.

        With continue-on-error set and a device already unreachable, this step
        can itself fail. That is worth a fault event rather than a silent skip
        -- the bench is left in an unknown state and the operator needs to
        know which plug.
        """
        self._publish(EventKind.MESSAGE, phase=Phase.RESTORE, detail="restoring")
        results = await asyncio.gather(
            *(s.restore() for s in sessions), return_exceptions=True
        )
        for session, result in zip(sessions, results, strict=True):
            if isinstance(result, BaseException):
                self._publish(
                    EventKind.FAULT,
                    device=session.profile_id,
                    phase=Phase.RESTORE,
                    action="restore",
                    result=Result.ERROR,
                    detail=f"could not restore {session.label}: {result}",
                )

    def _publish(
        self,
        kind: EventKind,
        *,
        device: str | None = None,
        cycle: int | None = None,
        phase: Phase | None = None,
        action: str | None = None,
        result: Result | None = None,
        detail: str | None = None,
    ) -> None:
        self._bus.publish(
            Event(
                kind=kind,
                timestamp=datetime.now().astimezone(),
                device=device,
                cycle=cycle,
                phase=phase,
                action=action,
                result=result,
                detail=detail,
            )
        )
