"""Smoke test: cycle a KP125M on and off a few times to prove auth + control work.

Credentials come from the environment:
    export KASA_USERNAME='you@example.com'
    export KASA_PASSWORD='...'
    .venv/bin/python scratch/kp125m_toggle.py --cycles 3 --on-time 5 --off-time 5

Deliberately has no retry or reconnect logic -- a failure here should stop the
script loudly rather than get papered over.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

from kasa import Credentials, Device, DeviceConfig, DeviceConnectionParameters
from kasa.deviceconfig import DeviceEncryptionType, DeviceFamily

DEFAULT_HOST = "192.168.10.17"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        # Keep the docstring's line breaks, and append each default.
        formatter_class=type(
            "HelpFormatter",
            (
                argparse.ArgumentDefaultsHelpFormatter,
                argparse.RawDescriptionHelpFormatter,
            ),
            {},
        ),
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Plug IP address.")
    parser.add_argument(
        "--on-time", type=float, default=5.0, help="Seconds to stay on."
    )
    parser.add_argument(
        "--off-time", type=float, default=5.0, help="Seconds to stay off."
    )
    parser.add_argument(
        "--cycles", type=int, default=3, help="Number of on/off pairs to run."
    )
    return parser.parse_args()


def credentials_from_env() -> Credentials:
    """Build credentials from the environment, exiting with help if unset."""
    username = os.environ.get("KASA_USERNAME")
    password = os.environ.get("KASA_PASSWORD")
    missing = [
        name
        for name, value in (("KASA_USERNAME", username), ("KASA_PASSWORD", password))
        if not value
    ]
    if missing:
        sys.exit(
            f"Missing {' and '.join(missing)} in the environment.\n"
            "Export your TP-Link cloud credentials in this shell, e.g.:\n"
            "    export KASA_USERNAME='you@example.com'\n"
            "    export KASA_PASSWORD='your-kasa-password'"
        )
    return Credentials(username, password)


def log(message: str) -> None:
    """Print a timestamped progress line."""
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


async def set_state(dev: Device, *, on: bool) -> None:
    """Set the relay and confirm the device actually reports the new state.

    turn_on/turn_off returning without raising only means the command was
    accepted, so read it back before believing it.
    """
    await (dev.turn_on() if on else dev.turn_off())
    await dev.update()
    wanted = "on" if on else "off"
    if dev.is_on is not on:
        raise RuntimeError(
            f"Asked the plug to turn {wanted}, but it reports "
            f"{'on' if dev.is_on else 'off'}."
        )
    log(f"plug is {wanted}")


async def main() -> None:
    """Connect to the plug and run the on/off cycles."""
    args = parse_args()

    # Connection parameters are hardcoded from the discovery result for this
    # plug, so there is no discovery round-trip on startup.
    config = DeviceConfig(
        host=args.host,
        credentials=credentials_from_env(),
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartKasaPlug,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            https=False,
        ),
    )

    # Device has no async context manager; disconnect() must be called
    # explicitly or aiohttp leaks the session on the way out.
    dev = await Device.connect(config=config)
    try:
        await dev.update()
        was_on = dev.is_on
        log(
            f"connected to {dev.alias} ({dev.model}) at {dev.host}, currently "
            f"{'on' if was_on else 'off'}"
        )

        try:
            for cycle in range(1, args.cycles + 1):
                log(f"--- cycle {cycle} of {args.cycles} ---")
                await set_state(dev, on=True)
                await asyncio.sleep(args.on_time)
                await set_state(dev, on=False)
                await asyncio.sleep(args.off_time)
        finally:
            # Leave the plug how we found it, including on Ctrl-C.
            log(f"restoring original state ({'on' if was_on else 'off'})")
            await set_state(dev, on=was_on)
    finally:
        await dev.disconnect()


try:
    asyncio.run(main())
except KeyboardInterrupt:
    log("interrupted")
