"""Module for cli light control commands."""

import asyncio
import sys
from typing import cast

import asyncclick as click

from kasa import (
    Credentials,
    Device,
)

from .common import echo, error, pass_dev_or_child


async def aioinput(string: str):
    """Non loop blocking get input."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda s=string: sys.stdout.write(s + " "))  # type: ignore[misc]

    return await loop.run_in_executor(None, sys.stdin.readline)


@click.command()
@click.option(
    "--cam-username",
    required=True,
    envvar="KASA_CAMERA_USERNAME",
    help="Camera account username address to authenticate to device.",
)
@click.option(
    "--cam-password",
    required=True,
    envvar="KASA_CAMERA_PASSWORD",
    help="Camera account password to use to authenticate to device.",
)
@pass_dev_or_child
async def listen(dev: Device, cam_username: str, cam_password: str) -> None:
    """Commands to control light settings."""
    try:
        import onvif  # type: ignore[import-untyped] # noqa: F401
    except ImportError:
        error("python-kasa must be installed with [onvif] extra for listen.")

    from kasa.smartcam.modules.listen import EventType, Listen

    listen: Listen = cast(Listen, dev.modules.get(Listen._module_name()))
    if not listen:
        error(f"Device {dev.host} does not support listening for events.")

    def on_event(event: EventType) -> None:
        echo(f"Device {dev.host} received event {event}")

    creds = Credentials(cam_username, cam_password)
    await listen.listen(on_event, creds)

    await aioinput("Listening, press enter to cancel\n")

    echo("Stopping listener")
    await listen.stop()
