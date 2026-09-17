"""The per-run CSV record."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

from gzplug.core.csvlog import COLUMNS, CsvRunLogger, run_filename
from gzplug.core.events import Event, EventBus, EventKind, Phase, Result, Sample


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


async def test_logger_writes_header_and_rows(tmp_path, bus: EventBus):
    path = tmp_path / "run.csv"
    now = datetime.now().astimezone()

    async with CsvRunLogger(path).attach(bus):
        bus.publish(Event(kind=EventKind.RUN_STARTED, timestamp=now))
        bus.publish(
            Event(
                kind=EventKind.COMMAND,
                timestamp=now,
                device="bench-a",
                cycle=1,
                phase=Phase.ON,
                action="turn_on",
                result=Result.OK,
                detail="plug is on",
                sample=Sample(
                    is_on=True,
                    power_w=12.5,
                    voltage_v=121.2,
                    current_a=0.103,
                    energy_today_kwh=0.02,
                ),
            )
        )

    rows = read_rows(path)
    assert list(rows[0]) == list(COLUMNS)
    command = rows[1]
    assert command["device"] == "bench-a"
    assert command["cycle"] == "1"
    assert command["phase"] == "on"
    assert command["action"] == "turn_on"
    assert command["result"] == "ok"
    assert command["power_w"] == "12.5"
    assert command["energy_today_kwh"] == "0.02"


async def test_events_without_metering_leave_energy_columns_blank(tmp_path, bus):
    path = tmp_path / "run.csv"
    async with CsvRunLogger(path).attach(bus):
        bus.publish(
            Event(
                kind=EventKind.MESSAGE,
                timestamp=datetime.now().astimezone(),
                detail="restoring",
            )
        )

    row = read_rows(path)[0]
    assert row["power_w"] == ""
    assert row["voltage_v"] == ""
    assert row["detail"] == "restoring"


async def test_queued_events_are_drained_on_exit(tmp_path, bus):
    """Nothing published before the context closes may be lost."""
    path = tmp_path / "run.csv"
    async with CsvRunLogger(path).attach(bus):
        for index in range(25):
            bus.publish(
                Event(
                    kind=EventKind.MESSAGE,
                    timestamp=datetime.now().astimezone(),
                    detail=f"event-{index}",
                )
            )

    assert len(read_rows(path)) == 25


async def test_elapsed_is_measured_from_the_run_start(tmp_path, bus):
    path = tmp_path / "run.csv"
    start = datetime.now().astimezone()

    async with CsvRunLogger(path).attach(bus):
        bus.publish(Event(kind=EventKind.RUN_STARTED, timestamp=start))
        bus.publish(
            Event(kind=EventKind.MESSAGE, timestamp=start + timedelta(seconds=2.5))
        )

    rows = read_rows(path)
    assert float(rows[0]["elapsed_s"]) == 0.0
    assert float(rows[1]["elapsed_s"]) == 2.5


def test_run_filename_is_sortable_and_windows_safe():
    when = datetime(2026, 9, 17, 14, 32, 1)
    assert run_filename("Bench 2 / plug A", when=when) == (
        "run_2026-09-17_143201_Bench-2-plug-A.csv"
    )
    assert run_filename("", when=when) == "run_2026-09-17_143201.csv"
