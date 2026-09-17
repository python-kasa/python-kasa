"""One plug, one connection, one place where device I/O is allowed.

The scratch scripts this replaces got two things right that are easy to lose
in a larger application, and both are preserved here:

* ``turn_on()`` returning without raising only means the command was
  *accepted*. The state is always read back and confirmed before the session
  claims success.
* :class:`~kasa.Device` has no async context manager, so ``disconnect()`` must
  be called explicitly or aiohttp leaks the session. Every exit path calls it.

What is added is the resilience a multi-hour bench run needs, and only when
the operator asks for it: with :attr:`RetryPolicy.enabled` false -- the
default -- any error stops the run loudly rather than getting papered over.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

from kasa import Device, KasaException, Module

from .events import DeviceInfo, Event, EventBus, EventKind, Phase, Result, Sample

if TYPE_CHECKING:
    from kasa import DeviceConfig

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

#: Errors that mean "the device did not do what we asked". Deliberately does
#: not include CancelledError, which must propagate so a stopped run stops.
_DEVICE_ERRORS = (KasaException, OSError, asyncio.TimeoutError)


class SessionFault(Exception):
    """An operation failed and its retry budget, if any, is exhausted."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How hard to try before giving up on a command.

    Disabled by default: a bench run that silently retried past a real fault
    would produce a clean-looking log of a test that did not happen.
    """

    enabled: bool = False
    max_attempts: int = 3
    initial_backoff_s: float = 1.0
    max_backoff_s: float = 30.0

    def backoff(self, attempt: int) -> float:
        """Seconds to wait after a failed 1-based *attempt*."""
        return min(self.initial_backoff_s * 2 ** (attempt - 1), self.max_backoff_s)

    @property
    def attempts(self) -> int:
        """Total tries allowed for one operation."""
        return self.max_attempts if self.enabled else 1


class PlugSession:
    """A connection to one plug, and the only code that talks to it.

    All device I/O is serialized through a lock, because the run engine and
    the periodic poller both drive the same :class:`~kasa.Device` and the
    library does not expect concurrent updates on one instance.
    """

    def __init__(
        self,
        profile_id: str,
        label: str,
        config: DeviceConfig,
        bus: EventBus,
        *,
        retry: RetryPolicy | None = None,
        settle_s: float = 0.0,
    ) -> None:
        """Create a session. No I/O happens until :meth:`connect`.

        :param settle_s: optional pause between issuing a state change and
            reading it back, for devices that report the old state briefly.
            Zero by default, which is what the KP125M needs.
        """
        self.profile_id = profile_id
        self.label = label
        self.config = config
        self._bus = bus
        self._retry = retry or RetryPolicy()
        self._settle_s = settle_s
        self._lock = asyncio.Lock()
        self._dev: Device | None = None
        self._original_state: bool | None = None
        self._fault_count = 0

    # -- properties ----------------------------------------------------

    @property
    def connected(self) -> bool:
        """True once :meth:`connect` has succeeded and before teardown."""
        return self._dev is not None

    @property
    def retry(self) -> RetryPolicy:
        """Current retry policy."""
        return self._retry

    @retry.setter
    def retry(self, policy: RetryPolicy) -> None:
        """Swap the policy between runs, when the operator changes the toggle."""
        self._retry = policy

    @property
    def fault_count(self) -> int:
        """Errors seen on this session, including ones that were retried."""
        return self._fault_count

    @property
    def original_state(self) -> bool | None:
        """Relay state at connect time, so a run can put it back."""
        return self._original_state

    @property
    def device(self) -> Device:
        """The underlying device, once connected."""
        if self._dev is None:
            raise SessionFault(f"{self.label}: not connected")
        return self._dev

    @property
    def host(self) -> str:
        """Address this session talks to."""
        return self.config.host

    # -- lifecycle -----------------------------------------------------

    async def connect(self) -> Sample:
        """Open the connection and capture the plug's starting state."""
        async with self._lock:
            self._dev = await self._attempt(
                "connect", self._do_connect, phase=Phase.SETUP
            )
            sample = await self._attempt("update", self._do_read, phase=Phase.SETUP)
            if self._original_state is None:
                self._original_state = sample.is_on
            self._publish(
                EventKind.CONNECTION,
                action="connect",
                result=Result.OK,
                phase=Phase.SETUP,
                detail=(
                    f"{self.device.alias} ({self.device.model}) at {self.host}, "
                    f"currently {'on' if sample.is_on else 'off'}"
                ),
                sample=sample,
            )
            return sample

    async def disconnect(self) -> None:
        """Close the connection. Safe to call more than once."""
        async with self._lock:
            dev, self._dev = self._dev, None
            if dev is None:
                return
            try:
                await dev.disconnect()
            except _DEVICE_ERRORS as exc:  # pragma: no cover - teardown only
                _LOGGER.warning("%s: error during disconnect: %s", self.label, exc)
            self._publish(
                EventKind.CONNECTION,
                action="disconnect",
                result=Result.OK,
                phase=Phase.TEARDOWN,
            )

    # -- operations ----------------------------------------------------

    async def read(self) -> Sample:
        """Refresh from the device and return the current reading."""
        async with self._lock:
            return await self._attempt("update", self._do_read)

    async def set_state(
        self,
        on: bool,
        *,
        cycle: int | None = None,
        phase: Phase | None = None,
    ) -> Sample:
        """Switch the relay and confirm the device agrees it happened."""
        wanted = "on" if on else "off"
        phase = phase or (Phase.ON if on else Phase.OFF)

        async def op() -> Sample:
            await (self.device.turn_on() if on else self.device.turn_off())
            if self._settle_s:
                await asyncio.sleep(self._settle_s)
            sample = await self._do_read()
            if sample.is_on is not on:
                # Accepting the command is not the same as performing it.
                raise SessionFault(
                    f"{self.label}: asked the plug to turn {wanted}, but it "
                    f"reports {'on' if sample.is_on else 'off'}"
                )
            return sample

        async with self._lock:
            sample = await self._attempt(f"turn_{wanted}", op, cycle=cycle, phase=phase)
            self._publish(
                EventKind.COMMAND,
                action=f"turn_{wanted}",
                result=Result.OK,
                cycle=cycle,
                phase=phase,
                detail=f"plug is {wanted}",
                sample=sample,
            )
            return sample

    async def restore(self) -> Sample | None:
        """Put the relay back to the state found at connect time."""
        if self._original_state is None:
            return None
        return await self.set_state(self._original_state, phase=Phase.RESTORE)

    # -- internals -----------------------------------------------------
    # Everything below assumes the caller holds ``self._lock``.

    async def _do_connect(self) -> Device:
        return await Device.connect(config=self.config)

    def _feature(self, name: str) -> Any:
        """Read a feature value, or None when the plug does not expose it.

        Features vary by model and firmware, so every read here is optional
        by design -- a plug without overheat reporting must still sample.
        """
        feature = self.device.features.get(name)
        if feature is None:
            return None
        try:
            return feature.value
        except KasaException:  # pragma: no cover - model-specific
            return None

    async def _do_read(self) -> Sample:
        dev = self.device
        await dev.update()
        energy = dev.modules.get(Module.Energy)
        return Sample(
            is_on=dev.is_on,
            power_w=energy.current_consumption if energy else None,
            voltage_v=energy.voltage if energy else None,
            current_a=energy.current if energy else None,
            energy_today_kwh=energy.consumption_today if energy else None,
            energy_month_kwh=energy.consumption_this_month if energy else None,
            overheated=self._feature("overheated"),
            overloaded=self._feature("overloaded"),
            rssi_dbm=self._feature("rssi"),
            signal_level=self._feature("signal_level"),
            on_since=dev.on_since,
        )

    def read_info(self) -> DeviceInfo:
        """Facts that do not change between polls, read after an update."""
        dev = self.device
        hw = dev.hw_info or {}
        return DeviceInfo(
            device_id=dev.device_id,
            mac=dev.mac,
            alias=dev.alias,
            model=dev.model,
            firmware=hw.get("sw_ver"),
            hardware=hw.get("hw_ver"),
            ssid=self._feature("ssid"),
            auto_off_enabled=self._feature("auto_off_enabled"),
            auto_off_minutes=self._feature("auto_off_minutes"),
            auto_update_enabled=self._feature("auto_update_enabled"),
            update_available=self._feature("update_available"),
            power_protection_w=self._feature("power_protection_threshold"),
            led_on=self._feature("led"),
        )

    async def _reconnect(self) -> None:
        """Best-effort teardown and redial between retry attempts."""
        dev, self._dev = self._dev, None
        if dev is not None:
            # Already broken; the redial is what matters.
            with contextlib.suppress(*_DEVICE_ERRORS):
                await dev.disconnect()
        self._dev = await Device.connect(config=self.config)

    async def _attempt(
        self,
        action: str,
        op: Callable[[], Awaitable[_T]],
        *,
        cycle: int | None = None,
        phase: Phase | None = None,
    ) -> _T:
        """Run *op*, retrying with backoff only if the policy allows it."""
        attempts = self._retry.attempts
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return await op()
            except (*_DEVICE_ERRORS, SessionFault) as exc:
                last_error = exc
                self._fault_count += 1
                final = attempt >= attempts
                self._publish(
                    EventKind.FAULT,
                    action=action,
                    result=Result.ERROR if final else Result.RETRY,
                    cycle=cycle,
                    phase=phase,
                    detail=f"attempt {attempt}/{attempts}: {exc}",
                )
                if final:
                    break
                await asyncio.sleep(self._retry.backoff(attempt))
                try:
                    await self._reconnect()
                except _DEVICE_ERRORS as reconnect_error:
                    # Keep going: the next attempt will fail and report, and
                    # a transient redial failure is not itself the fault.
                    _LOGGER.debug(
                        "%s: reconnect failed: %s", self.label, reconnect_error
                    )

        raise SessionFault(
            f"{self.label}: {action} failed: {last_error}"
        ) from last_error

    def _publish(
        self,
        kind: EventKind,
        *,
        action: str | None = None,
        result: Result | None = None,
        cycle: int | None = None,
        phase: Phase | None = None,
        detail: str | None = None,
        sample: Sample | None = None,
    ) -> None:
        self._bus.publish(
            Event(
                kind=kind,
                timestamp=datetime.now().astimezone(),
                device=self.profile_id,
                cycle=cycle,
                phase=phase,
                action=action,
                result=result,
                detail=detail,
                sample=sample,
            )
        )
