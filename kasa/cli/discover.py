"""Module for cli discovery commands."""

from __future__ import annotations

import asyncio

import asyncclick as click
from pydantic.v1 import ValidationError

from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    Discover,
    UnsupportedDeviceError,
)
from kasa.discover import DiscoveryResult

from .common import echo


@click.command()
@click.pass_context
async def discover(ctx):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    username = ctx.parent.params["username"]
    password = ctx.parent.params["password"]
    discovery_timeout = ctx.parent.params["discovery_timeout"]
    timeout = ctx.parent.params["timeout"]
    port = ctx.parent.params["port"]

    credentials = Credentials(username, password) if username and password else None

    sem = asyncio.Semaphore()
    discovered = dict()
    unsupported = []
    auth_failed = []

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError):
        unsupported.append(unsupported_exception)
        async with sem:
            if unsupported_exception.discovery_result:
                echo("== Unsupported device ==")
                _echo_discovery_info(unsupported_exception.discovery_result)
                echo()
            else:
                echo("== Unsupported device ==")
                echo(f"\t{unsupported_exception}")
                echo()

    echo(f"Discovering devices on {target} for {discovery_timeout} seconds")

    from .device import state

    async def print_discovered(dev: Device):
        async with sem:
            try:
                await dev.update()
            except AuthenticationError:
                auth_failed.append(dev._discovery_info)
                echo("== Authentication failed for device ==")
                _echo_discovery_info(dev._discovery_info)
                echo()
            else:
                ctx.parent.obj = dev
                await ctx.parent.invoke(state)
                discovered[dev.host] = dev.internal_state
            echo()

    discovered_devices = await Discover.discover(
        target=target,
        discovery_timeout=discovery_timeout,
        on_discovered=print_discovered,
        on_unsupported=print_unsupported,
        port=port,
        timeout=timeout,
        credentials=credentials,
    )

    for device in discovered_devices.values():
        await device.protocol.close()

    echo(f"Found {len(discovered)} devices")
    if unsupported:
        echo(f"Found {len(unsupported)} unsupported devices")
    if auth_failed:
        echo(f"Found {len(auth_failed)} devices that failed to authenticate")

    return discovered


def _echo_dictionary(discovery_info: dict):
    echo("\t[bold]== Discovery information ==[/bold]")
    for key, value in discovery_info.items():
        key_name = " ".join(x.capitalize() or "_" for x in key.split("_"))
        key_name_and_spaces = "{:<15}".format(key_name + ":")
        echo(f"\t{key_name_and_spaces}{value}")


def _echo_discovery_info(discovery_info):
    # We don't have discovery info when all connection params are passed manually
    if discovery_info is None:
        return

    if "system" in discovery_info and "get_sysinfo" in discovery_info["system"]:
        _echo_dictionary(discovery_info["system"]["get_sysinfo"])
        return

    try:
        dr = DiscoveryResult(**discovery_info)
    except ValidationError:
        _echo_dictionary(discovery_info)
        return

    echo("\t[bold]== Discovery Result ==[/bold]")
    echo(f"\tDevice Type:        {dr.device_type}")
    echo(f"\tDevice Model:       {dr.device_model}")
    echo(f"\tIP:                 {dr.ip}")
    echo(f"\tMAC:                {dr.mac}")
    echo(f"\tDevice Id (hash):   {dr.device_id}")
    echo(f"\tOwner (hash):       {dr.owner}")
    echo(f"\tHW Ver:             {dr.hw_ver}")
    echo(f"\tSupports IOT Cloud: {dr.is_support_iot_cloud}")
    echo(f"\tOBD Src:            {dr.obd_src}")
    echo(f"\tFactory Default:    {dr.factory_default}")
    echo(f"\tEncrypt Type:       {dr.mgt_encrypt_schm.encrypt_type}")
    echo(f"\tSupports HTTPS:     {dr.mgt_encrypt_schm.is_support_https}")
    echo(f"\tHTTP Port:          {dr.mgt_encrypt_schm.http_port}")
    echo(f"\tLV (Login Level):   {dr.mgt_encrypt_schm.lv}")


async def find_host_from_alias(alias, target="255.255.255.255", timeout=1, attempts=3):
    """Discover a device identified by its alias."""
    for _attempt in range(1, attempts):
        found_devs = await Discover.discover(target=target, timeout=timeout)
        for _ip, dev in found_devs.items():
            if dev.alias.lower() == alias.lower():
                host = dev.host
                return host

    return None
