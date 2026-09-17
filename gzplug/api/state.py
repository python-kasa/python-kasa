"""Application state shared by every request.

The GUI needs something the CLI did not: plugs stay connected while the app is
open, so the operator can see live state and flip a relay by hand without
starting a run. That means connecting must be *tolerant* -- one unplugged
bench position cannot stop the other three from being usable, which is why
this does not use :meth:`DeviceRegistry.connect_all`, whose all-or-nothing
behaviour is right for a run and wrong for a dashboard.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from kasa import Discover, KasaException

from ..config import AppConfig, BenchProfile, runs_dir
from ..core.csvlog import CsvRunLogger, run_filename
from ..core.events import Event, EventBus, EventKind, Sample
from ..core.poller import Poller
from ..core.registry import MAX_DEVICES, DeviceRegistry, RegistryError
from ..core.runner import RunEngine, RunPlan, RunState
from ..core.session import PlugSession, RetryPolicy, SessionFault

_LOGGER = logging.getLogger(__name__)


#: Raw device errors are unreadable on a card -- an aiohttp
#: ClientConnectorError repr runs to several hundred characters of
#: ConnectionKey and SSLContext addresses. Map the ones a bench actually hits
#: to a sentence, and keep the original for anyone who wants it.
_ERROR_HINTS: tuple[tuple[str, str], ...] = (
    (
        "did not match our challenge",
        "Authentication failed - check the account credentials, or re-pair this plug.",
    ),
    ("Host is down", "Host is down - the plug is not answering at this address."),
    ("Network is unreachable", "Network unreachable from this machine."),
    ("Connection refused", "Connection refused by the plug."),
    ("Name or service not known", "Address could not be resolved."),
    ("Temporary failure in name resolution", "Address could not be resolved."),
    ("Timeout", "Timed out contacting the plug."),
    ("timed out", "Timed out contacting the plug."),
    (
        "TPAP",
        "Unsupported encryption (TPAP). Enable Third-Party "
        "Compatibility in the Tapo app.",
    ),
)

_MAX_ERROR_CHARS = 160


def summarize_error(error: BaseException) -> tuple[str, str]:
    """Return a one-line summary and the untouched original."""
    full = str(error)
    for needle, message in _ERROR_HINTS:
        if needle in full:
            return message, full
    if len(full) <= _MAX_ERROR_CHARS:
        return full, full
    return full[:_MAX_ERROR_CHARS].rstrip() + "...", full


@dataclass
class DeviceView:
    """What the browser shows for one bench position."""

    id: str
    label: str
    host: str
    connected: bool = False
    error: str | None = None
    error_detail: str | None = None
    #: Set when the plug was found at a different address than the one saved.
    relocated_from: str | None = None
    #: Static facts from DeviceInfo, as a plain dict for the browser.
    info: dict[str, Any] = field(default_factory=dict)
    alias: str | None = None
    model: str | None = None
    is_on: bool | None = None
    power_w: float | None = None
    voltage_v: float | None = None
    current_a: float | None = None
    energy_today_kwh: float | None = None
    energy_month_kwh: float | None = None
    overheated: bool | None = None
    overloaded: bool | None = None
    rssi_dbm: int | None = None
    signal_level: int | None = None
    on_since: str | None = None
    faults: int = 0
    updated_at: str | None = None

    def apply(self, sample: Sample, when: datetime) -> None:
        """Fold in a fresh reading."""
        self.is_on = sample.is_on
        self.power_w = sample.power_w
        self.voltage_v = sample.voltage_v
        self.current_a = sample.current_a
        self.energy_today_kwh = sample.energy_today_kwh
        self.energy_month_kwh = sample.energy_month_kwh
        self.overheated = sample.overheated
        self.overloaded = sample.overloaded
        self.rssi_dbm = sample.rssi_dbm
        self.signal_level = sample.signal_level
        self.on_since = (
            sample.on_since.isoformat(timespec="seconds") if sample.on_since else None
        )
        self.updated_at = when.isoformat(timespec="seconds")


@dataclass
class AppState:
    """Everything the running application owns."""

    config: AppConfig = field(default_factory=AppConfig)
    bus: EventBus = field(default_factory=EventBus)
    registry: DeviceRegistry = field(default_factory=DeviceRegistry)
    views: dict[str, DeviceView] = field(default_factory=dict)
    engine: RunEngine | None = None
    poller: Poller | None = None
    _run_task: asyncio.Task[None] | None = None
    _cache_task: asyncio.Task[None] | None = None
    _csv_path: Path | None = None

    # -- lifecycle -----------------------------------------------------

    async def startup(self) -> None:
        """Load config, connect what we can, and start sampling."""
        self.config = AppConfig.load()
        self.engine = RunEngine(self.registry, self.bus)
        self.poller = Poller(
            self.registry, self.bus, interval_s=self.config.poll_interval_s
        )
        self._cache_task = asyncio.create_task(
            self._absorb_events(), name="gzplug-state-cache"
        )
        await self.reload_devices()
        self.poller.start()

    async def shutdown(self) -> None:
        """Stop everything and let go of the plugs."""
        await self.stop_run()
        if self.poller is not None:
            await self.poller.stop()
        if self._cache_task is not None:
            self._cache_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cache_task
        await self.registry.disconnect_all()
        self.registry.clear()

    # -- devices -------------------------------------------------------

    async def reload_devices(self) -> None:
        """Rebuild sessions from the saved profiles, tolerating failures."""
        if self.running:
            raise RuntimeError("cannot change devices while a run is in progress")

        await self.registry.disconnect_all()
        self.registry.clear()
        self.views.clear()

        for profile in self.config.profiles[:MAX_DEVICES]:
            view = DeviceView(id=profile.id, label=profile.label, host=profile.host)
            self.views[profile.id] = view
            session = PlugSession(
                profile.id,
                profile.label,
                profile.device_config(self.config.credentials),
                self.bus,
            )
            self.registry.add(session)
            await self._connect_one(session, view, profile)

    async def _connect_one(
        self,
        session: PlugSession,
        view: DeviceView,
        profile: BenchProfile | None = None,
    ) -> None:
        """Connect one plug, recording rather than raising on failure.

        If the saved address fails and we know which plug this is, look for it
        elsewhere on the network before giving up: a DHCP lease change is the
        ordinary reason a bench position stops answering, and re-pairing by
        hand for that is busywork.
        """
        try:
            sample = await session.connect()
        except (SessionFault, KasaException, OSError) as exc:
            if profile is not None and await self._relocate(session, view, profile):
                return
            view.connected = False
            view.error, view.error_detail = summarize_error(exc)
            _LOGGER.warning("could not connect %s: %s", session.label, exc)
            return
        self._mark_connected(session, view, sample, profile)

    def _mark_connected(
        self,
        session: PlugSession,
        view: DeviceView,
        sample: Sample,
        profile: BenchProfile | None,
    ) -> None:
        """Record a good connection, and learn the plug's identity."""
        info = session.read_info()
        view.connected = True
        view.error = None
        view.error_detail = None
        view.host = session.host
        view.info = asdict(info)
        view.alias = info.alias
        view.model = info.model
        view.apply(sample, datetime.now().astimezone())

        # Backfill identity for profiles saved before it was tracked, so the
        # next address change can be recovered from.
        if profile is not None and info.device_id and not profile.device_id:
            profile.device_id = info.device_id
            profile.mac = info.mac
            self.config.save()

    async def _relocate(
        self, session: PlugSession, view: DeviceView, profile: BenchProfile
    ) -> bool:
        """Search the network for this plug's new address. True if found."""
        if not profile.device_id:
            return False

        _LOGGER.info(
            "%s did not answer at %s; searching for it by device id",
            profile.label,
            profile.host,
        )
        try:
            found = await Discover.discover(
                credentials=self.config.credentials, discovery_timeout=5
            )
        except (KasaException, OSError) as exc:
            _LOGGER.debug("relocation scan failed: %s", exc)
            return False

        for host, device in found.items():
            if device.device_id != profile.device_id:
                await device.disconnect()
                continue
            await device.disconnect()
            old_host = profile.host
            profile.with_host(host)
            self.config.save()
            session.config = profile.device_config(self.config.credentials)
            try:
                sample = await session.connect()
            except (SessionFault, KasaException, OSError) as exc:
                _LOGGER.warning(
                    "found %s at %s but could not connect: %s", profile.label, host, exc
                )
                return False
            self._mark_connected(session, view, sample, profile)
            view.relocated_from = old_host
            _LOGGER.info("%s moved from %s to %s", profile.label, old_host, host)
            return True

        for device in found.values():
            await device.disconnect()
        return False

    async def reconnect(self, profile_id: str) -> DeviceView:
        """Retry a plug the operator has just fixed."""
        session = self.registry.get(profile_id)
        view = self.views[profile_id]
        profile = next((p for p in self.config.profiles if p.id == profile_id), None)
        await session.disconnect()
        await self._connect_one(session, view, profile)
        return view

    async def set_device_state(self, profile_id: str, on: bool) -> DeviceView:
        """Flip one relay by hand, outside any run."""
        if self.running:
            raise RuntimeError("cannot switch a plug by hand while a run is running")
        session = self.registry.get(profile_id)
        sample = await session.set_state(on)
        view = self.views[profile_id]
        view.apply(sample, datetime.now().astimezone())
        return view

    # -- runs ----------------------------------------------------------

    @property
    def running(self) -> bool:
        """True while a run is in flight."""
        return self.engine is not None and self.engine.running

    async def start_run(self, plan: RunPlan) -> Path:
        """Begin a run and return the path of the CSV it will write."""
        if self.engine is None:
            raise RuntimeError("application is not started")
        if self.running:
            raise RuntimeError("a run is already in progress")

        missing = [
            pid
            for pid in plan.devices
            if not (view := self.views.get(pid)) or not view.connected
        ]
        if missing:
            raise RuntimeError(f"not connected: {', '.join(missing)}")

        # The policy is per-run, so rebuild the sessions' retry behaviour to
        # match what the operator ticked before starting.
        policy = RetryPolicy(enabled=plan.continue_on_error)
        for session in self.registry.sessions:
            session.retry = policy

        path = runs_dir() / run_filename(plan.label)
        self._csv_path = path
        self._run_task = asyncio.create_task(
            self._run_with_logging(plan, path), name="gzplug-run-wrapper"
        )
        return path

    async def _run_with_logging(self, plan: RunPlan, path: Path) -> None:
        """Hold the CSV open for exactly as long as the run lasts.

        A failed or aborted run is not re-raised here: the engine has already
        recorded it in its status and published a RUN_FINISHED event, and
        nothing is waiting on this task to hear about it.
        """
        if self.engine is None:  # pragma: no cover - startup guarantees this
            return
        async with CsvRunLogger(path).attach(self.bus):
            task = self.engine.start(plan)
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - surfaced via the bus
                _LOGGER.info("run ended with an error: %s", exc)

    async def stop_run(self) -> None:
        """Ask a running run to stop; plugs are still restored."""
        if self.engine is not None:
            await self.engine.stop()
        task, self._run_task = self._run_task, None
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001 - surfaced via the bus
                _LOGGER.info("run wrapper ended with an error: %s", exc)

    # -- snapshot ------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Full state, as sent on page load and after every mutation."""
        status = self.engine.status if self.engine else None
        return {
            "configured": self.config.configured,
            "username": self.config.username,
            "maxDevices": MAX_DEVICES,
            "pollIntervalS": self.config.poll_interval_s,
            "devices": [vars(v) for v in self.views.values()],
            "run": {
                "state": status.state.value if status else RunState.IDLE.value,
                "cycle": status.cycle if status else 0,
                "cycles": status.plan.cycles if status and status.plan else 0,
                "error": status.error if status else None,
                "faults": status.faults if status else {},
                "startedAt": (
                    status.started_at.isoformat(timespec="seconds")
                    if status and status.started_at
                    else None
                ),
                "csv": self._csv_path.name if self._csv_path else None,
            },
        }

    # -- internals -----------------------------------------------------

    async def _absorb_events(self) -> None:
        """Keep the per-device view current. A third bus subscriber."""
        with self.bus.subscribe() as queue:
            while True:
                event = await queue.get()
                self._absorb(event)

    def _absorb(self, event: Event) -> None:
        if event.device is None:
            return
        view = self.views.get(event.device)
        if view is None:
            return
        if event.sample is not None:
            view.apply(event.sample, event.timestamp)
        if event.kind is EventKind.FAULT:
            with contextlib.suppress(RegistryError):
                view.faults = self.registry.get(event.device).fault_count
        if event.kind is EventKind.CONNECTION and event.action == "disconnect":
            view.connected = False
