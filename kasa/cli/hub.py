"""Hub-specific commands."""

import asyncclick as click

from .common import (
    echo,
    pass_dev,
)


@click.group()
async def hub():
    """Commands controling child devices."""


@hub.command(name="list")
@pass_dev
async def hub_list(dev):
    """List children."""
    for c in dev.children:
        echo(f"{c.device_id}: {c}")


@hub.command(name="pair")
@click.option("--timeout", default=10)
@pass_dev
async def hub_pair(dev, timeout):
    """Pair new device."""
    if "ChildSetupModule" not in dev.modules:
        echo(f"{dev} is not a hub.")
        return

    echo(f"Finding new devices for {timeout} seconds...")
    cs = dev.modules["ChildSetupModule"]
    return await cs.pair(timeout=timeout)


@hub.command(name="unpair")
@click.argument("device_id")
@pass_dev
async def hub_unpair(dev, device_id: str):
    """Unpair given device."""
    if "ChildSetupModule" not in dev.modules:
        echo(f"{dev} is not a hub.")
        return

    cs = dev.modules["ChildSetupModule"]
    res = await cs.unpair(device_id=device_id)
    echo(f"Unpaired {device_id} (if it was paired)")
    return res
