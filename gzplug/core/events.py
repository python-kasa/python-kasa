"""Run events and the bus that fans them out to subscribers.

Every observable thing that happens during a run -- a command issued, a state
read back, a periodic sample, a fault -- is published here as an
:class:`Event`. Subscribers consume the same stream for different purposes:

* the CSV logger writes the run record,
* the WebSocket broadcaster pushes live status to the browser,
* the rule engine (planned) reacts to one plug's state by driving another.

That last one is why this module exists. Routing everything through a bus
means multi-plug interdependence arrives as a new subscriber rather than as
surgery on :mod:`gzplug.core.runner`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

_LOGGER = logging.getLogger(__name__)

#: Bounded subscribers drop events rather than stall the run loop. The CSV
#: logger subscribes unbounded, so the durable record is never the thing
#: dropped.
DEFAULT_QUEUE_SIZE = 1000


class EventKind(StrEnum):
    """What kind of thing happened."""

    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    CYCLE_STARTED = "cycle_started"
    COMMAND = "command"
    SAMPLE = "sample"
    FAULT = "fault"
    CONNECTION = "connection"
    MESSAGE = "message"


class Phase(StrEnum):
    """Which part of a run an event belongs to."""

    SETUP = "setup"
    ON = "on"
    OFF = "off"
    RESTORE = "restore"
    TEARDOWN = "teardown"


class Result(StrEnum):
    """How an operation turned out."""

    OK = "ok"
    RETRY = "retry"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Sample:
    """One reading of a plug's state, metering and health.

    Every field is optional: a plug without energy monitoring, or one whose
    metering has not reported yet, still produces a useful state sample.

    The device keeps no per-hour or per-day history, only the running totals
    below, so anything a future energy view plots has to come from these
    being written down as a run happens.
    """

    is_on: bool | None = None
    #: Instantaneous power draw, in watts.
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    #: Energy used today and this month, in kWh -- the units the library
    #: reports, not the milliwatt-hours the device returns on the wire. The
    #: KP125M does not support a since-reboot total, so these are the only
    #: sums available.
    energy_today_kwh: float | None = None
    energy_month_kwh: float | None = None
    #: Protection trips. On a power-product bench these are the readings that
    #: explain why a plug stopped behaving, so they go in the run record.
    overheated: bool | None = None
    overloaded: bool | None = None
    #: Radio quality, which is usually what is behind a run full of retries.
    rssi_dbm: int | None = None
    signal_level: int | None = None
    #: When the relay last switched on.
    on_since: datetime | None = None


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Facts about a plug that do not change between polls.

    Read once at connect. Two of these are operational traps rather than
    trivia: a plug with auto-off enabled will end a long endurance run by
    itself, and one with auto-update enabled can be pushed onto firmware this
    build cannot talk to.
    """

    device_id: str | None = None
    mac: str | None = None
    alias: str | None = None
    model: str | None = None
    firmware: str | None = None
    hardware: str | None = None
    ssid: str | None = None
    auto_off_enabled: bool | None = None
    auto_off_minutes: int | None = None
    auto_update_enabled: bool | None = None
    update_available: bool | None = None
    power_protection_w: float | None = None
    led_on: bool | None = None


@dataclass(frozen=True, slots=True)
class Event:
    """Something that happened during a run."""

    kind: EventKind
    timestamp: datetime
    #: Profile id of the device concerned, or None for run-wide events.
    device: str | None = None
    cycle: int | None = None
    phase: Phase | None = None
    action: str | None = None
    result: Result | None = None
    detail: str | None = None
    sample: Sample | None = None


class EventBus:
    """Fan-out of :class:`Event` to any number of queue subscribers.

    Publishing is synchronous and never blocks, so device code can emit from
    anywhere without awaiting a slow consumer.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    @contextmanager
    def subscribe(
        self, *, maxsize: int = DEFAULT_QUEUE_SIZE
    ) -> Iterator[asyncio.Queue[Event]]:
        """Subscribe for the duration of the context.

        :param maxsize: queue bound; pass 0 for an unbounded queue, which is
            what a subscriber that must not miss events should do.
        """
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    def publish(self, event: Event) -> None:
        """Deliver an event to every subscriber, dropping on full queues."""
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A bounded subscriber falling behind loses events; it must
                # not be allowed to stall the device loop driving the bench.
                _LOGGER.warning(
                    "Dropped %s event: subscriber queue full", event.kind.value
                )

    @property
    def subscriber_count(self) -> int:
        """Number of live subscribers, for diagnostics and tests."""
        return len(self._subscribers)
