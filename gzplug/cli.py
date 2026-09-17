"""Headless command line for the bench plug controller.

This exists so Phase 1 is useful before any UI does: it replaces
``scratch/kp125m_toggle.py`` with something that discovers plugs, remembers
them, and leaves a CSV record of what a run actually did.

Uses argparse rather than the asyncclick the library CLI is built on, to keep
the frozen Windows build free of an async CLI framework's plugin machinery.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from datetime import datetime

from kasa import Device, Discover, KasaException, UnsupportedDeviceError

from .config import AppConfig, BenchProfile, config_path, runs_dir
from .core.csvlog import CsvRunLogger, run_filename
from .core.events import Event, EventBus, EventKind, Result
from .core.poller import Poller
from .core.registry import DeviceRegistry, RegistryError
from .core.runner import RunEngine, RunFailed, RunPlan
from .core.session import PlugSession, RetryPolicy

_LOGGER = logging.getLogger(__name__)


# -- console output ----------------------------------------------------


def _log(message: str) -> None:
    """Print a timestamped progress line, as the scratch scripts did."""
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


class ConsolePrinter:
    """Echoes run events to the terminal. Another bus subscriber, nothing more."""

    #: Samples arrive every couple of seconds and would drown the log.
    _QUIET = frozenset({EventKind.SAMPLE})

    @contextlib.asynccontextmanager
    async def attach(self, bus: EventBus):  # noqa: ANN201
        """Print events for the duration of the context."""
        with bus.subscribe() as queue:
            task = asyncio.create_task(self._consume(queue), name="gzplug-console")
            try:
                yield self
            finally:
                await asyncio.sleep(0)  # let the last events through
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _consume(self, queue: asyncio.Queue[Event]) -> None:
        while True:
            self._print(await queue.get())

    def _print(self, event: Event) -> None:
        if event.kind in self._QUIET:
            return
        prefix = f"{event.device}: " if event.device else ""
        marker = "!! " if event.result is Result.ERROR else ""
        detail = event.detail or event.action or event.kind.value
        _log(f"{marker}{prefix}{detail}")


# -- commands ----------------------------------------------------------


async def cmd_creds(args: argparse.Namespace) -> int:
    """Store the shared test-team account credentials."""
    config = AppConfig.load()
    config.username = args.username
    config.password = args.password
    path = config.save()
    print(f"Credentials saved to {path}")
    print("Note: stored in plaintext by design. Do not reuse this password.")
    return 0


async def cmd_discover(args: argparse.Namespace) -> int:
    """Scan the network and optionally save what turns up."""
    config = AppConfig.load()
    if not config.configured:
        print("No credentials set. Run 'gzplug creds' first.", file=sys.stderr)
        return 2

    # A plug the library cannot speak to still answers discovery. Without this
    # callback it is dropped at debug level and looks like a missing device,
    # sending you off to debug the network instead of the encryption scheme.
    unsupported: list[UnsupportedDeviceError] = []

    async def on_unsupported(error: UnsupportedDeviceError) -> None:
        unsupported.append(error)

    print(f"Scanning {args.target} for {args.timeout}s ...")
    found = await Discover.discover(
        target=args.target,
        credentials=config.credentials,
        discovery_timeout=args.timeout,
        on_unsupported=on_unsupported,
    )

    if unsupported:
        print(f"\n{len(unsupported)} device(s) answered but are NOT supported:")
        for error in unsupported:
            print(f"  {error.host or '?':<16} {error}")
        print(
            "  -> In the Tapo app: Profile > Third Party Services >\n"
            "     Third-Party Compatibility. Turning that on reverts the plug\n"
            "     to KLAP, which this build supports. The phone must be on the\n"
            "     same network as the plug.\n"
        )

    if not found:
        print("No supported devices found.")
        print(
            "On Windows, check that the firewall prompt for this app was "
            "allowed -- a blocked broadcast finds nothing."
        )
        print("If you know the plug's IP, use 'gzplug add --host <ip>' instead.")
        return 1

    for host, device in sorted(found.items()):
        print(f"  {host:<16} {device.alias or '(no alias)':<24} {device.model}")
        if args.save:
            profile = BenchProfile.from_device(device)
            config.upsert(profile)
            print(f"      saved as profile id '{profile.id}'")

    if args.save:
        config.save()
        print(f"\nProfiles written to {config_path()}")
    return 0


async def _probe(args: argparse.Namespace, config: AppConfig) -> Device | None:
    """Unicast discovery of one address."""
    return await Discover.discover_single(
        args.host,
        credentials=config.credentials,
        discovery_timeout=args.timeout,
    )


async def cmd_add(args: argparse.Namespace) -> int:
    """Add a plug by IP address, without relying on a broadcast.

    Discovery is a LAN broadcast, so it cannot cross a subnet and is blocked
    outright by client isolation on many corporate access points. This probes
    one address directly, which works in both cases.
    """
    config = AppConfig.load()
    if not config.configured:
        print("No credentials set. Run 'gzplug creds' first.", file=sys.stderr)
        return 2

    print(f"Contacting {args.host} ...")
    try:
        device = await _probe(args, config)
    except UnsupportedDeviceError as error:
        print(
            f"{args.host} answered, but this build cannot talk to it:", file=sys.stderr
        )
        print(f"  {error}", file=sys.stderr)
        print(
            "\nNewer TP-Link firmware uses TPAP encryption, which python-kasa\n"
            "does not support yet (upstream issue #1590). To use this plug now,\n"
            "open the Tapo app: Profile > Third Party Services >\n"
            "Third-Party Compatibility. That reverts it to KLAP. The phone must\n"
            "be on the same network as the plug.",
            file=sys.stderr,
        )
        return 1

    if device is None:
        print(f"No response from {args.host}.", file=sys.stderr)
        print(
            "Check the plug is powered, joined to WiFi (not in pairing mode), "
            "and reachable -- try 'ping " + args.host + "'.",
            file=sys.stderr,
        )
        return 1

    try:
        profile = BenchProfile.from_device(device, args.label)
        config.upsert(profile)
        config.save()
        print(
            f"Saved '{profile.id}' -- {device.alias or '(no alias)'} "
            f"({device.model}) at {device.host}"
        )
    finally:
        await device.disconnect()
    return 0


async def cmd_devices(args: argparse.Namespace) -> int:
    """List saved bench profiles."""
    config = AppConfig.load()
    if not config.profiles:
        print("No saved profiles. Run 'gzplug discover --save'.")
        return 0
    for profile in config.profiles:
        host = profile.config.get("host", "?")
        print(f"  {profile.id:<20} {profile.label:<28} {host}")
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    """Execute a cycle run and write its CSV."""
    config = AppConfig.load()
    if not config.configured:
        print("No credentials set. Run 'gzplug creds' first.", file=sys.stderr)
        return 2

    retry = RetryPolicy(enabled=args.continue_on_error)
    bus = EventBus()
    registry = DeviceRegistry()
    try:
        for profile_id in args.device:
            profile = config.get(profile_id)
            registry.add(
                PlugSession(
                    profile.id,
                    profile.label,
                    profile.device_config(config.credentials),
                    bus,
                    retry=retry,
                )
            )
    except KeyError as exc:
        print(f"Unknown device: {exc}. Try 'gzplug devices'.", file=sys.stderr)
        return 2
    except RegistryError as exc:
        print(f"{exc}", file=sys.stderr)
        return 2

    plan = RunPlan(
        devices=tuple(args.device),
        cycles=args.cycles,
        on_time_s=args.on_time,
        off_time_s=args.off_time,
        continue_on_error=args.continue_on_error,
        restore_state=not args.no_restore,
        label=args.label,
    )
    csv_path = runs_dir() / run_filename(args.label)
    engine = RunEngine(registry, bus)
    poller = Poller(registry, bus, interval_s=config.poll_interval_s)

    async with CsvRunLogger(csv_path).attach(bus), ConsolePrinter().attach(bus):
        try:
            await registry.connect_all()
        except RegistryError as exc:
            print(f"{exc}", file=sys.stderr)
            return 1

        poller.start()
        try:
            await engine.execute(plan)
        except RunFailed as exc:
            _log(f"run failed: {exc}")
            return 1
        except asyncio.CancelledError:
            _log("interrupted")
            return 130
        finally:
            await poller.stop()
            await registry.disconnect_all()

    print(f"\nRun record: {csv_path}")
    return 0


async def cmd_ui(args: argparse.Namespace) -> int:
    """Serve the web interface on the CLI's existing event loop.

    Imported lazily so the rest of the CLI still works when the web
    dependencies in gzplug/requirements.txt have not been installed.
    """
    try:
        from .__main__ import serve
    except ImportError as exc:
        print(f"The web interface needs extra packages: {exc}", file=sys.stderr)
        print(
            "Install them with:  pip install -r gzplug/requirements.txt",
            file=sys.stderr,
        )
        return 2

    return await serve(
        args.host, args.port, open_browser=not args.no_browser, verbose=args.verbose
    )


# -- entry point -------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Assemble the command line."""
    parser = argparse.ArgumentParser(
        prog="gzplug", description="Goal Zero bench plug controller."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    creds = sub.add_parser("creds", help="Store shared account credentials.")
    creds.add_argument("--username", required=True)
    creds.add_argument("--password", required=True)
    creds.set_defaults(func=cmd_creds)

    discover = sub.add_parser("discover", help="Scan the network for plugs.")
    discover.add_argument("--target", default="255.255.255.255")
    discover.add_argument("--timeout", type=int, default=5)
    discover.add_argument(
        "--save", action="store_true", help="Save results as bench profiles."
    )
    discover.set_defaults(func=cmd_discover)

    add = sub.add_parser(
        "add", help="Add a plug by IP, when discovery cannot reach it."
    )
    add.add_argument("--host", required=True, help="Plug IP address.")
    add.add_argument("--label", default="", help="Name for this bench position.")
    add.add_argument("--timeout", type=int, default=5)
    add.set_defaults(func=cmd_add)

    devices = sub.add_parser("devices", help="List saved bench profiles.")
    devices.set_defaults(func=cmd_devices)

    ui = sub.add_parser("ui", help="Open the local web interface.")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-browser", action="store_true")
    ui.set_defaults(func=cmd_ui)

    run = sub.add_parser("run", help="Run an on/off cycle test.")
    run.add_argument(
        "--device",
        action="append",
        required=True,
        metavar="PROFILE_ID",
        help="Profile to drive; repeat for up to four plugs.",
    )
    run.add_argument("--cycles", type=int, default=3)
    run.add_argument("--on-time", type=float, default=5.0)
    run.add_argument("--off-time", type=float, default=5.0)
    run.add_argument("--label", default="", help="Name for the CSV file.")
    run.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Retry and press on through faults instead of stopping.",
    )
    run.add_argument(
        "--no-restore",
        action="store_true",
        help="Leave the plugs as the run left them.",
    )
    run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        _log("interrupted")
        return 130
    except KasaException as exc:
        print(f"Device error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
