"""Module for cli discovery commands."""

from __future__ import annotations

import asyncio
from pprint import pformat as pf
from typing import TYPE_CHECKING, cast

import asyncclick as click

from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    Discover,
    UnsupportedDeviceError,
)
from kasa.discover import (
    NEW_DISCOVERY_REDACTORS,
    ConnectAttempt,
    DeviceDict,
    DiscoveredRaw,
    DiscoveryResult,
    OnDiscoveredCallable,
    OnDiscoveredRawCallable,
    OnUnsupportedCallable,
)
from kasa.iot.iotdevice import _extract_sys_info
from kasa.protocols.iotprotocol import REDACTORS as IOT_REDACTORS
from kasa.protocols.protocol import redact_data

from ..json import dumps as json_dumps
from .common import echo, error


@click.group(invoke_without_command=True)
@click.pass_context
async def discover(ctx: click.Context):
    """Discover devices in the network."""
    if ctx.invoked_subcommand is None:
        return await ctx.invoke(detail)


@discover.result_callback()
@click.pass_context
async def _close_protocols(ctx: click.Context, discovered: DeviceDict):
    """Close all the device protocols if discover was invoked directly by the user."""
    if _discover_is_root_cmd(ctx):
        for dev in discovered.values():
            await dev.disconnect()
    return discovered


def _discover_is_root_cmd(ctx: click.Context) -> bool:
    """Will return true if discover was invoked directly by the user."""
    root_ctx = ctx.find_root()
    return (
        root_ctx.invoked_subcommand is None or root_ctx.invoked_subcommand == "discover"
    )


@discover.command()
@click.pass_context
async def detail(ctx: click.Context) -> DeviceDict:
    """Discover devices in the network using udp broadcasts."""
    unsupported = []
    auth_failed = []
    sem = asyncio.Semaphore()

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError) -> None:
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

    async def print_discovered(dev: Device) -> None:
        if TYPE_CHECKING:
            assert ctx.parent
        async with sem:
            try:
                await dev.update()
            except AuthenticationError:
                if TYPE_CHECKING:
                    assert dev._discovery_info
                auth_failed.append(dev._discovery_info)
                echo("== Authentication failed for device ==")
                _echo_discovery_info(dev._discovery_info)
                echo()
            else:
                ctx.parent.obj = dev
                await ctx.parent.invoke(state)
            echo()

    discovered = await _discover(
        ctx,
        print_discovered=print_discovered if _discover_is_root_cmd(ctx) else None,
        print_unsupported=print_unsupported,
    )
    if ctx.find_root().params["host"]:
        return discovered

    echo(f"Found {len(discovered)} devices")
    if unsupported:
        echo(f"Found {len(unsupported)} unsupported devices")
    if auth_failed:
        echo(f"Found {len(auth_failed)} devices that failed to authenticate")

    return discovered


@discover.command()
@click.option(
    "--redact/--no-redact",
    default=False,
    is_flag=True,
    type=bool,
    help="Set flag to redact sensitive data from raw output.",
)
@click.pass_context
async def raw(ctx: click.Context, redact: bool) -> DeviceDict:
    """Return raw discovery data returned from devices."""

    def print_raw(discovered: DiscoveredRaw):
        if redact:
            redactors = (
                NEW_DISCOVERY_REDACTORS
                if discovered["meta"]["port"] == Discover.DISCOVERY_PORT_2
                else IOT_REDACTORS
            )
            discovered["discovery_response"] = redact_data(
                discovered["discovery_response"], redactors
            )
        echo(json_dumps(discovered, indent=True))

    return await _discover(ctx, print_raw=print_raw, do_echo=False)


@discover.command()
@click.pass_context
async def list(ctx: click.Context) -> DeviceDict:
    """List devices in the network in a table using udp broadcasts."""
    sem = asyncio.Semaphore()

    async def print_discovered(dev: Device):
        cparams = dev.config.connection_type
        infostr = (
            f"{dev.host:<15} {dev.model:<9} {cparams.device_family.value:<20} "
            f"{cparams.encryption_type.value:<7} {cparams.https:<5} "
            f"{cparams.login_version or '-':<3}"
        )
        async with sem:
            try:
                await dev.update()
            except AuthenticationError:
                echo(f"{infostr} - Authentication failed")
            except TimeoutError:
                echo(f"{infostr} - Timed out")
            except Exception as ex:
                echo(f"{infostr} - Error: {ex}")
            else:
                echo(f"{infostr} {dev.alias}")

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError):
        if host := unsupported_exception.host:
            echo(f"{host:<15} UNSUPPORTED DEVICE")

    echo(
        f"{'HOST':<15} {'MODEL':<9} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} "
        f"{'HTTPS':<5} {'LV':<3} {'ALIAS'}"
    )
    discovered = await _discover(
        ctx,
        print_discovered=print_discovered,
        print_unsupported=print_unsupported,
        do_echo=False,
    )
    return discovered


async def _discover(
    ctx: click.Context,
    *,
    print_discovered: OnDiscoveredCallable | None = None,
    print_unsupported: OnUnsupportedCallable | None = None,
    print_raw: OnDiscoveredRawCallable | None = None,
    do_echo=True,
) -> DeviceDict:
    params = ctx.find_root().params
    target = params["target"]
    username = params["username"]
    password = params["password"]
    discovery_timeout = params["discovery_timeout"]
    timeout = params["timeout"]
    host = params["host"]
    port = params["port"]

    credentials = Credentials(username, password) if username and password else None

    if host:
        host = cast(str, host)
        echo(f"Discovering device {host} for {discovery_timeout} seconds")
        dev = await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
            on_unsupported=print_unsupported,
            on_discovered_raw=print_raw,
        )
        if dev:
            if print_discovered:
                await print_discovered(dev)
            return {host: dev}
        else:
            return {}
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
        on_discovered_raw=print_raw,
    )

    return discovered_devices


@discover.command()
@click.pass_context
async def config(ctx: click.Context) -> DeviceDict:
    """Bypass udp discovery and try to show connection config for a device.

    Bypasses udp discovery and shows the parameters required to connect
    directly to the device.
    """
    params = ctx.find_root().params
    username = params["username"]
    password = params["password"]
    timeout = params["timeout"]
    host = params["host"]
    port = params["port"]

    if not host:
        error("--host option must be supplied to discover config")

    credentials = Credentials(username, password) if username and password else None

    host_port = host + (f":{port}" if port else "")

    def on_attempt(connect_attempt: ConnectAttempt, success: bool) -> None:
        prot, tran, dev, https = connect_attempt
        key_str = (
            f"{prot.__name__} + {tran.__name__} + {dev.__name__}"
            f" + {'https' if https else 'http'}"
        )
        result = "succeeded" if success else "failed"
        msg = f"Attempt to connect to {host_port} with {key_str} {result}"
        echo(msg)

    dev = await Discover.try_connect_all(
        host, credentials=credentials, timeout=timeout, port=port, on_attempt=on_attempt
    )
    if dev:
        cparams = dev.config.connection_type
        echo("Managed to connect, cli options to connect are:")
        echo(
            f"--device-family {cparams.device_family.value} "
            f"--encrypt-type {cparams.encryption_type.value} "
            f"{'--https' if cparams.https else '--no-https'}"
        )
        return {host: dev}
    else:
        error(f"Unable to connect to {host}")


def _echo_dictionary(discovery_info: dict) -> None:
    echo("\t[bold]== Discovery information ==[/bold]")
    for key, value in discovery_info.items():
        key_name = " ".join(x.capitalize() or "_" for x in key.split("_"))
        key_name_and_spaces = "{:<15}".format(key_name + ":")
        echo(f"\t{key_name_and_spaces}{value}")


def _echo_discovery_info(discovery_info: dict) -> None:
    # We don't have discovery info when all connection params are passed manually
    if discovery_info is None:
        return

    if sysinfo := _extract_sys_info(discovery_info):
        _echo_dictionary(sysinfo)
        return

    try:
        dr = DiscoveryResult.from_dict(discovery_info)
    except Exception:
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
    _conditional_echo("OBD Src", dr.obd_src)
    _conditional_echo("Factory Default", dr.factory_default)
    _conditional_echo("Encrypt Type", dr.encrypt_type)
    if mgt_encrypt_schm := dr.mgt_encrypt_schm:
        _conditional_echo("Encrypt Type", mgt_encrypt_schm.encrypt_type)
        _conditional_echo("Supports HTTPS", mgt_encrypt_schm.is_support_https)
        _conditional_echo("HTTP Port", mgt_encrypt_schm.http_port)
        _conditional_echo("Login version", mgt_encrypt_schm.lv)
    _conditional_echo("Encrypt info", pf(dr.encrypt_info) if dr.encrypt_info else None)
    _conditional_echo("Decrypted", pf(dr.decrypted_data) if dr.decrypted_data else None)


async def find_dev_from_alias(
    alias: str,
    credentials: Credentials | None,
    target: str = "255.255.255.255",
    timeout: int = 5,
    attempts: int = 3,
) -> Device | None:
    """Discover a device identified by its alias."""
    found_event = asyncio.Event()
    found_device = []
    seen_hosts = set()

    async def on_discovered(dev: Device):
        if dev.host in seen_hosts:
            return
        seen_hosts.add(dev.host)
        try:
            await dev.update()
        except Exception as ex:
            echo(f"Error querying device {dev.host}: {ex}")
            return
        finally:
            await dev.protocol.close()
        if not dev.alias:
            echo(f"Skipping device {dev.host} with no alias")
            return
        if dev.alias.lower() == alias.lower():
            found_device.append(dev)
            found_event.set()

    async def do_discover():
        for _ in range(1, attempts):
            await Discover.discover(
                target=target,
                timeout=timeout,
                credentials=credentials,
                on_discovered=on_discovered,
            )
            if found_event.is_set():
                break
        found_event.set()

    asyncio.create_task(do_discover())
    await found_event.wait()
    return found_device[0] if found_device else None
