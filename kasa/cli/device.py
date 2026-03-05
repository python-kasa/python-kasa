"""Module for cli device commands."""

from __future__ import annotations

from pprint import pformat as pf
from typing import TYPE_CHECKING

import asyncclick as click

from kasa import (
    Device,
    Module,
)
from kasa.smart import SmartDevice

from .common import (
    echo,
    error,
    pass_dev,
    pass_dev_or_child,
)


@click.group()
@pass_dev_or_child
def device(dev) -> None:
    """Commands to control basic device settings."""


@device.command()
@pass_dev_or_child
@click.pass_context
async def state(ctx, dev: Device):
    """Print out device state and versions."""
    from .feature import _echo_all_features

    verbose = ctx.parent.params.get("verbose", False) if ctx.parent else False

    echo(f"[bold]== {dev.alias} - {dev.model} ==[/bold]")
    echo(f"Host: {dev.host}")
    echo(f"Port: {dev.port}")
    echo(f"Device state: {dev.is_on}")

    echo(f"Time:         {dev.time} (tz: {dev.timezone})")
    echo(
        f"Hardware:     {dev.device_info.hardware_version}"
        f"{' (' + dev.region + ')' if dev.region else ''}"
    )
    echo(
        f"Firmware:     {dev.device_info.firmware_version}"
        f"{' ' + build if (build := dev.device_info.firmware_build) else ''}"
    )
    echo(f"MAC (rssi):   {dev.mac} ({dev.rssi})")
    if verbose:
        echo(f"Location:     {dev.location}")

    echo()
    _echo_all_features(dev.features, verbose=verbose)

    if verbose:
        echo("\n[bold]== Modules ==[/bold]")
        for module in dev.modules.values():
            echo(f"[green]+ {module}[/green]")

    if dev.children:
        echo("\n[bold]== Children ==[/bold]")
        for child in dev.children:
            _echo_all_features(
                child.features,
                title_prefix=f"{child.alias} ({child.model})",
                verbose=verbose,
                indent="\t",
            )
            if verbose:
                echo(f"\n\t[bold]== Child {child.alias} Modules ==[/bold]")
                for module in child.modules.values():
                    echo(f"\t[green]+ {module}[/green]")
        echo()

    if verbose:
        echo("\n\t[bold]== Protocol information ==[/bold]")
        echo(f"\tCredentials hash:  {dev.credentials_hash}")
        echo()
        from .discover import _echo_discovery_info

        if TYPE_CHECKING:
            assert dev._discovery_info
        _echo_discovery_info(dev._discovery_info)

    return dev.internal_state


@device.command()
@pass_dev_or_child
async def sysinfo(dev):
    """Print out full system information."""
    echo("== System info ==")
    echo(pf(dev.sys_info))
    return dev.sys_info


@device.command()
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def on(dev: Device, transition: int):
    """Turn the device on."""
    echo(f"Turning on {dev.alias}")
    return await dev.turn_on(transition=transition)


@device.command
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def off(dev: Device, transition: int):
    """Turn the device off."""
    echo(f"Turning off {dev.alias}")
    return await dev.turn_off(transition=transition)


@device.command()
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def toggle(dev: Device, transition: int):
    """Toggle the device on/off."""
    if dev.is_on:
        echo(f"Turning off {dev.alias}")
        return await dev.turn_off(transition=transition)

    echo(f"Turning on {dev.alias}")
    return await dev.turn_on(transition=transition)


@device.command()
@click.argument("state", type=bool, required=False)
@pass_dev_or_child
async def led(dev: Device, state):
    """Get or set (Plug's) led state."""
    if not (led := dev.modules.get(Module.Led)):
        error("Device does not support led.")
        return
    if state is not None:
        echo(f"Turning led to {state}")
        return await led.set_led(state)
    else:
        echo(f"LED state: {led.led}")
        return led.led


@device.command()
@click.argument("new_alias", required=False, default=None)
@pass_dev_or_child
async def alias(dev, new_alias):
    """Get or set the device (or plug) alias."""
    if new_alias is not None:
        echo(f"Setting alias to {new_alias}")
        res = await dev.set_alias(new_alias)
        await dev.update()
        echo(f"Alias set to: {dev.alias}")
        return res

    echo(f"Alias: {dev.alias}")
    if dev.children:
        for plug in dev.children:
            echo(f"  * {plug.alias}")

    return dev.alias


@device.command()
@click.option("--delay", default=1)
@pass_dev
async def reboot(plug, delay):
    """Reboot the device."""
    echo("Rebooting the device..")
    return await plug.reboot(delay)


@device.command()
@pass_dev
async def factory_reset(plug):
    """Reset device to factory settings."""
    click.confirm(
        "Do you really want to reset the device to factory settings?", abort=True
    )

    return await plug.factory_reset()


@device.command()
@pass_dev
@click.option(
    "--username", required=True, prompt=True, help="New username to set on the device"
)
@click.option(
    "--password", required=True, prompt=True, help="New password to set on the device"
)
async def update_credentials(dev, username, password):
    """Update device credentials for authenticated devices."""
    if not isinstance(dev, SmartDevice):
        error("Credentials can only be updated on authenticated devices.")

    click.confirm("Do you really want to replace the existing credentials?", abort=True)

    return await dev.update_credentials(username, password)


@device.command(name="logs")
@pass_dev_or_child
async def child_logs(dev):
    """Print child device trigger logs."""
    if logs := dev.modules.get(Module.TriggerLogs):
        await dev.update(update_children=True)
        for entry in logs.logs:
            print(entry)
