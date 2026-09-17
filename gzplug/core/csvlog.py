"""Per-run CSV record, written as the run happens.

Subscribes unbounded, so the durable record is never what gets dropped when a
subscriber falls behind. Energy columns are populated on every row from the
poller's samples, which makes this file both the run record and the raw
material for the planned energy-history view.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .events import Event, EventBus, EventKind

_LOGGER = logging.getLogger(__name__)

COLUMNS = (
    "timestamp_iso",
    "elapsed_s",
    "device",
    "cycle",
    "phase",
    "event",
    "action",
    "result",
    "detail",
    "power_w",
    "voltage_v",
    "current_a",
    "energy_today_kwh",
    "energy_month_kwh",
    # Protection trips and radio quality explain most of what goes wrong on a
    # bench, so they belong in the record rather than only on screen.
    "overheated",
    "overloaded",
    "rssi_dbm",
)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def run_filename(label: str = "", *, when: datetime | None = None) -> str:
    """Build a run filename that is safe on Windows and sorts by time."""
    when = when or datetime.now().astimezone()
    stamp = when.strftime("%Y-%m-%d_%H%M%S")
    slug = _UNSAFE.sub("-", label).strip("-")
    return f"run_{stamp}_{slug}.csv" if slug else f"run_{stamp}.csv"


class CsvRunLogger:
    """Writes one CSV per run, driven by the event bus."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._t0: datetime | None = None
        self._rows = 0

    @property
    def rows_written(self) -> int:
        """Rows written so far, excluding the header."""
        return self._rows

    @asynccontextmanager
    async def attach(self, bus: EventBus) -> AsyncIterator[CsvRunLogger]:
        """Subscribe and consume for the duration of the context.

        Subscribing happens before the body runs, so no event emitted by the
        run being started inside the context can be missed.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (
            bus.subscribe(maxsize=0) as queue,
            self.path.open("w", newline="", encoding="utf-8") as handle,
        ):
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            consumer = asyncio.create_task(
                self._consume(queue, writer, handle), name="gzplug-csv"
            )
            try:
                yield self
            finally:
                await self._drain(queue, writer, handle)
                consumer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await consumer
                handle.flush()

    async def _consume(
        self, queue: asyncio.Queue[Event], writer: csv.DictWriter, handle: TextIO
    ) -> None:
        while True:
            event = await queue.get()
            self._write(event, writer, handle)

    async def _drain(
        self, queue: asyncio.Queue[Event], writer: csv.DictWriter, handle: TextIO
    ) -> None:
        """Write whatever is still queued once the run is over."""
        while True:
            try:
                event = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            self._write(event, writer, handle)

    def _write(self, event: Event, writer: csv.DictWriter, handle: TextIO) -> None:
        if self._t0 is None or event.kind is EventKind.RUN_STARTED:
            self._t0 = event.timestamp
        sample = event.sample
        writer.writerow(
            {
                "timestamp_iso": event.timestamp.isoformat(timespec="milliseconds"),
                "elapsed_s": f"{(event.timestamp - self._t0).total_seconds():.3f}",
                "device": event.device or "",
                "cycle": event.cycle if event.cycle is not None else "",
                "phase": event.phase.value if event.phase else "",
                "event": event.kind.value,
                "action": event.action or "",
                "result": event.result.value if event.result else "",
                "detail": event.detail or "",
                "power_w": _num(sample.power_w) if sample else "",
                "voltage_v": _num(sample.voltage_v) if sample else "",
                "current_a": _num(sample.current_a) if sample else "",
                "energy_today_kwh": _num(sample.energy_today_kwh) if sample else "",
                "energy_month_kwh": _num(sample.energy_month_kwh) if sample else "",
                "overheated": _flag(sample.overheated) if sample else "",
                "overloaded": _flag(sample.overloaded) if sample else "",
                "rssi_dbm": _num(sample.rssi_dbm) if sample else "",
            }
        )
        # Flushed per row: a run that dies on a bench PC should still leave
        # everything it had recorded up to that moment.
        handle.flush()
        self._rows += 1


def _num(value: float | None) -> str:
    """Format a metering value, leaving unsupported readings blank."""
    return "" if value is None else f"{value:g}"


def _flag(value: bool | None) -> str:
    """Format a protection flag.

    Blank means the plug does not report it, which is not the same as
    reporting false -- a run record should not imply a check that never ran.
    """
    return "" if value is None else ("1" if value else "0")
