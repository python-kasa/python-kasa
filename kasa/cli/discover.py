"""Module for cli discovery commands."""

from __future__ import annotations

import asyncio
from pprint import pformat as pf

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

from .common import echo, error


@click.group(invoke_without_command=True)
@click.pass_context
async def discover(ctx):
    """Discover devices in the network."""
    if ctx.invoked_subcommand is None:
        return await ctx.invoke(detail)


@discover.command()
@click.pass_context
async def detail(ctx):
    """Discover devices in the network using udp broadcasts."""
    unsupported = []
    auth_failed = []
    sem = asyncio.Semaphore()

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
            echo()

    discovered = await _discover(ctx, print_discovered, print_unsupported)
    if ctx.parent.parent.params["host"]:
        return discovered

    echo(f"Found {len(discovered)} devices")
    if unsupported:
        echo(f"Found {len(unsupported)} unsupported devices")
    if auth_failed:
        echo(f"Found {len(auth_failed)} devices that failed to authenticate")

    return discovered


@discover.command()
@click.pass_context
async def list(ctx):
    """List devices in the network in a table using udp broadcasts."""
    sem = asyncio.Semaphore()

    async def print_discovered(dev: Device):
        cparams = dev.config.connection_type
        infostr = (
            f"{dev.host:<15} {cparams.device_family.value:<20} "
            f"{cparams.encryption_type.value:<7}"
        )
        async with sem:
            try:
                await dev.update()
            except AuthenticationError:
                echo(f"{infostr} - Authentication failed")
            else:
                echo(f"{infostr} {dev.alias}")

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError):
        if host := unsupported_exception.host:
            echo(f"{host:<15} UNSUPPORTED DEVICE")

    echo(f"{'HOST':<15} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} {'ALIAS'}")
    return await _discover(ctx, print_discovered, print_unsupported, do_echo=False)


async def _discover(ctx, print_discovered, print_unsupported, *, do_echo=True):
    params = ctx.parent.parent.params
    target = params["target"]
    username = params["username"]
    password = params["password"]
    discovery_timeout = params["discovery_timeout"]
    timeout = params["timeout"]
    host = params["host"]
    port = params["port"]

    credentials = Credentials(username, password) if username and password else None

    if host:
        echo(f"Discovering device {host} for {discovery_timeout} seconds")
        return await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
            on_unsupported=print_unsupported,
        )
    if do_echo:
        echo(f"Discovering devices on {target} for {discovery_timeout} seconds")
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

    return discovered_devices


@discover.command()
@click.pass_context
async def config(ctx):
    """Bypass udp discovery and try to show connection config for a device.

    Bypasses udp discovery and shows the parameters required to connect
    directly to the device.
    """
    params = ctx.parent.parent.params
    username = params["username"]
    password = params["password"]
    timeout = params["timeout"]
    host = params["host"]
    port = params["port"]

    if not host:
        error("--host option must be supplied to discover config")

    credentials = Credentials(username, password) if username and password else None

    dev = await Discover.try_connect_all(
        host, credentials=credentials, timeout=timeout, port=port
    )
    if dev:
        cparams = dev.config.connection_type
        echo("Managed to connect, cli options to connect are:")
        echo(
            f"--device-family {cparams.device_family.value} "
            f"--encrypt-type {cparams.encryption_type.value} "
            f"{'--https' if cparams.https else '--no-https'}"
        )
    else:
        error(f"Unable to connect to {host}")


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

    def _conditional_echo(label, value):
        if value:
            ws = " " * (19 - len(label))
            echo(f"\t{label}:{ws}{value}")

    echo("\t[bold]== Discovery Result ==[/bold]")
    _conditional_echo("Device Type", dr.device_type)
    _conditional_echo("Device Model", dr.device_model)
    _conditional_echo("Device Name", dr.device_name)
    _conditional_echo("IP", dr.ip)
    _conditional_echo("MAC", dr.mac)
    _conditional_echo("Device Id (hash)", dr.device_id)
    _conditional_echo("Owner (hash)", dr.owner)
    _conditional_echo("FW Ver", dr.firmware_version)
    _conditional_echo("HW Ver", dr.hw_ver)
    _conditional_echo("HW Ver", dr.hardware_version)
    _conditional_echo("Supports IOT Cloud", dr.is_support_iot_cloud)
    _conditional_echo("OBD Src", dr.owner)
    _conditional_echo("Factory Default", dr.factory_default)
    _conditional_echo("Encrypt Type", dr.mgt_encrypt_schm.encrypt_type)
    _conditional_echo("Encrypt Type", dr.encrypt_type)
    _conditional_echo("Supports HTTPS", dr.mgt_encrypt_schm.is_support_https)
    _conditional_echo("HTTP Port", dr.mgt_encrypt_schm.http_port)
    _conditional_echo("Encrypt info", pf(dr.encrypt_info) if dr.encrypt_info else None)
    _conditional_echo("Decrypted", pf(dr.decrypted_data) if dr.decrypted_data else None)


async def find_host_from_alias(alias, target="255.255.255.255", timeout=1, attempts=3):
    """Discover a device identified by its alias."""
    for _attempt in range(1, attempts):
        found_devs = await Discover.discover(target=target, timeout=timeout)
        for _ip, dev in found_devs.items():
            if dev.alias.lower() == alias.lower():
                host = dev.host
                return host

    return None
