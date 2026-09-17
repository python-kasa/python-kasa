"""Live updates to the browser.

The socket is a third subscriber on the same bus the CSV logger and the state
cache use -- it adds no path of its own into the device layer, so a browser
that is slow, closed, or never opened cannot affect a run.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..core.events import Event, EventBus
from .state import AppState

_LOGGER = logging.getLogger(__name__)


def event_to_dict(event: Event) -> dict[str, Any]:
    """Serialize an event for the browser."""
    sample = event.sample
    return {
        "kind": event.kind.value,
        "timestamp": event.timestamp.isoformat(timespec="milliseconds"),
        "device": event.device,
        "cycle": event.cycle,
        "phase": event.phase.value if event.phase else None,
        "action": event.action,
        "result": event.result.value if event.result else None,
        "detail": event.detail,
        "sample": None
        if sample is None
        else {
            "isOn": sample.is_on,
            "powerW": sample.power_w,
            "voltageV": sample.voltage_v,
            "currentA": sample.current_a,
            "energyTodayKwh": sample.energy_today_kwh,
            "energyMonthKwh": sample.energy_month_kwh,
            "overheated": sample.overheated,
            "overloaded": sample.overloaded,
            "rssiDbm": sample.rssi_dbm,
            "signalLevel": sample.signal_level,
            "onSince": (
                sample.on_since.isoformat(timespec="seconds")
                if sample.on_since
                else None
            ),
        },
    }


async def stream(websocket: WebSocket, state: AppState, bus: EventBus) -> None:
    """Push a snapshot, then every event, until the browser goes away."""
    await websocket.accept()
    try:
        await websocket.send_json({"type": "snapshot", "data": state.snapshot()})
    except (WebSocketDisconnect, RuntimeError):
        return

    with bus.subscribe() as queue:
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(
                    {
                        "type": "event",
                        "data": event_to_dict(event),
                        # The snapshot rides along so the browser never has to
                        # reconstruct run state from a stream of deltas.
                        "state": state.snapshot(),
                    }
                )
        except (WebSocketDisconnect, asyncio.CancelledError):
            raise
        except RuntimeError as exc:  # socket closed mid-send
            _LOGGER.debug("websocket closed: %s", exc)
        finally:
            with contextlib.suppress(RuntimeError):
                await websocket.close()
