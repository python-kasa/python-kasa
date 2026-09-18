"""Module for cli discovery commands."""

from __future__ import annotations

import asyncio
import builtins
from dataclasses import dataclass
from pprint import pformat as pf
from typing import TYPE_CHECKING, Any, cast

import asyncclick as click

from kasa import (
    AuthenticationError,
    Credentials,
    Device,
    DeviceConnectionParameters,
    Discover,
    DiscoveryAuthenticationError,
    KasaException,
    UnsupportedAuthenticationError,
    UnsupportedDeviceError,
)
from kasa.device_factory import ConnectAttempt
from kasa.discover import (
    TDP_DISCOVERY_REDACTORS,
    DeviceDict,
    DiscoveredRaw,
    DiscoveryResult,
    OnAuthenticationErrorCallable,
    OnDiscoveredCallable,
    OnDiscoveredRawCallable,
    OnUnsupportedCallable,
    select_discovery_response,
)
from kasa.iot.iotdevice import extract_sys_info
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


@dataclass(frozen=True)
class _DiscoveryListInfo:
    """Connection information displayed by ``discover list``."""

    host: str
    model: str | None = None
    device_family: str | None = None
    encryption_type: str | None = None
    https: bool | None = None
    login_version: int | None = None
    klap_version: int | None = None


def _format_connection_options(cparams: DeviceConnectionParameters) -> str:
    """Return CLI options that recreate direct connection parameters."""
    options = [
        f"--device-family {cparams.device_family.value}",
        f"--encrypt-type {cparams.encryption_type.value}",
    ]
    if cparams.login_version is not None:
        options.append(f"--login-version {cparams.login_version}")
    if cparams.klap_version is not None:
        options.append(f"--klap-version {cparams.klap_version}")
    options.append("--https" if cparams.https else "--no-https")
    return " ".join(options)


def _display_value(value: Any) -> str:
    """Return one display-table value, preserving false and zero values."""
    return "-" if value is None or value == "" else str(value)


def _get_discovery_list_info(
    host: str,
    *,
    device: Device | None = None,
    discovery_info: dict[str, Any] | None = None,
) -> _DiscoveryListInfo:
    """Return consistent list information from a device or discovery response."""
    info = _DiscoveryListInfo(host=host)
    if isinstance(discovery_info, dict):
        if sysinfo := extract_sys_info(discovery_info):
            device_family = sysinfo.get("mic_type", sysinfo.get("type"))
            model = sysinfo.get("model")
            if isinstance(model, str):
                model, _, _ = model.partition("(")
            info = _DiscoveryListInfo(
                host=host,
                model=model,
                device_family=device_family,
                encryption_type="XOR",
                https=device_family == "IOT.IPCAMERA",
                login_version=(
                    sysinfo.get("stream_version")
                    if device_family == "IOT.IPCAMERA"
                    else None
                ),
            )
        else:
            result = discovery_info.get("result", discovery_info)
            if isinstance(result, dict):
                model = result.get("device_model")
                if isinstance(model, str):
                    model, _, _ = model.partition("(")
                device_family = result.get("device_type")
                encryption_scheme = result.get("mgt_encrypt_schm")
                if not isinstance(encryption_scheme, dict):
                    encryption_scheme = {}
                encrypt_info = result.get("encrypt_info")
                if not isinstance(encrypt_info, dict):
                    encrypt_info = {}
                encryption_type = encryption_scheme.get(
                    "encrypt_type"
                ) or encrypt_info.get("sym_schm")
                info = _DiscoveryListInfo(
                    host=host,
                    model=model,
                    device_family=device_family,
                    encryption_type=encryption_type,
                    https=encryption_scheme.get("is_support_https"),
                    login_version=encryption_scheme.get("lv"),
                    klap_version=(
                        encryption_scheme.get("new_klap")
                        if isinstance(device_family, str)
                        and device_family.startswith("IOT.")
                        and encryption_type == "KLAP"
                        else None
                    ),
                )

    if device is None:
        return info

    cparams = device.config.connection_type
    return _DiscoveryListInfo(
        host=host,
        model=info.model or device.model,
        device_family=info.device_family or cparams.device_family.value,
        encryption_type=info.encryption_type or cparams.encryption_type.value,
        https=info.https if info.https is not None else cparams.https,
        login_version=(
            info.login_version
            if info.login_version is not None
            else cparams.login_version
        ),
        klap_version=(
            info.klap_version if info.klap_version is not None else cparams.klap_version
        ),
    )


def _format_discovery_source(response: DiscoveredRaw | None) -> str:
    """Return a compact discovery source and port label."""
    if response is None:
        return "-"
    meta = response["meta"]
    source = meta.get("source")
    if source is None:
        source = (
            "tdp"
            if meta["port"] in (Discover.DISCOVERY_PORT_2, Discover.DISCOVERY_PORT_3)
            else "udp"
        )
    return f"{source.upper()}/{meta['port']}"


def _format_discovery_list_row(
    info: _DiscoveryListInfo,
    *,
    source: str,
    result: str,
) -> str:
    """Format one complete ``discover list`` row."""
    return (
        f"{info.host:<15} {_display_value(info.model):<9} "
        f"{_display_value(info.device_family):<20} "
        f"{_display_value(info.encryption_type):<7} "
        f"{_display_value(info.https):<5} "
        f"{_display_value(info.login_version):<3} "
        f"{_display_value(info.klap_version):<3} "
        f"{source:<9} {result}"
    )


def _connection_parameters_from_discovery(
    response: DiscoveredRaw,
    device: Device | None,
) -> DeviceConnectionParameters | None:
    """Return connection parameters from an authoritative raw response."""
    if device is not None:
        return device.config.connection_type

    meta = response["meta"]
    source = meta.get("source")
    if source is None:
        source = (
            "tdp"
            if meta["port"] in (Discover.DISCOVERY_PORT_2, Discover.DISCOVERY_PORT_3)
            else "udp"
        )
    discovery_info = response["discovery_response"]
    if source == "tdp":
        result = discovery_info.get("result")
        if not isinstance(result, dict):
            return None
        try:
            return DiscoveryResult.from_dict(result).to_connection_parameters()
        except Exception:  # pragma: no cover - defensive raw-response handling
            return None

    if not (sysinfo := extract_sys_info(discovery_info)):
        return None
    device_family = sysinfo.get("mic_type", sysinfo.get("type"))
    if not isinstance(device_family, str):
        return None
    try:
        return DeviceConnectionParameters.from_values(
            device_family,
            "XOR",
            login_version=(
                sysinfo.get("stream_version")
                if device_family == "IOT.IPCAMERA"
                else None
            ),
            https=device_family == "IOT.IPCAMERA",
        )
    except KasaException:
        return None


@discover.command()
@click.pass_context
async def detail(ctx: click.Context) -> DeviceDict:
    """Discover devices in the network using broadcast discovery."""
    unsupported: dict[str, UnsupportedDeviceError] = {}
    auth_failed: dict[str, DiscoveryAuthenticationError] = {}
    sem = asyncio.Semaphore()

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError) -> None:
        host = unsupported_exception.host or "unknown"
        unsupported[host] = unsupported_exception
        async with sem:
            if isinstance(unsupported_exception, UnsupportedAuthenticationError):
                echo("== Unsupported device authentication ==")
            else:
                echo("== Unsupported device ==")
            if unsupported_exception.discovery_result:
                echo_discovery_info(unsupported_exception.discovery_result)
            else:
                echo(f"\t{unsupported_exception}")
            if isinstance(unsupported_exception, UnsupportedAuthenticationError):
                source = unsupported_exception.onboarding_source or "unknown"
                echo(f"\tOnboarding source: {source}")
                echo(
                    "\tReset and provision this device using a supported "
                    "TP-Link onboarding method."
                )
            echo()

    async def print_authentication_error(
        authentication_error: DiscoveryAuthenticationError,
    ) -> None:
        host = authentication_error.host or "unknown"
        auth_failed[host] = authentication_error
        async with sem:
            echo("== Authentication failed for device ==")
            if authentication_error.discovery_result:
                echo_discovery_info(authentication_error.discovery_result)
            else:
                echo(f"\t{authentication_error}")
            echo()
            echo()

    from .device import state

    async def print_discovered(dev: Device) -> None:
        if TYPE_CHECKING:
            assert ctx.parent
        await dev.update()
        async with sem:
            ctx.parent.obj = dev
            await ctx.parent.invoke(state)
            echo()

    discovered = await _discover(
        ctx,
        print_discovered=print_discovered if _discover_is_root_cmd(ctx) else None,
        print_unsupported=print_unsupported,
        print_authentication_error=print_authentication_error,
    )
    if ctx.find_root().params["host"]:
        if unsupported or auth_failed:
            for dev in discovered.values():
                await dev.disconnect()
            raise click.ClickException("The requested device could not be queried")
        return discovered

    found_hosts = set(discovered) | set(unsupported) | set(auth_failed)
    echo(f"Found {len(found_hosts)} devices")
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
            meta = discovered["meta"]
            source = meta.get("source")
            if source is None:
                source = (
                    "tdp"
                    if meta["port"]
                    in (Discover.DISCOVERY_PORT_2, Discover.DISCOVERY_PORT_3)
                    else "udp"
                )
            redactors = TDP_DISCOVERY_REDACTORS if source == "tdp" else IOT_REDACTORS
            discovered["discovery_response"] = redact_data(
                discovered["discovery_response"], redactors
            )
        echo(json_dumps(discovered, indent=True))

    return await _discover(ctx, print_raw=print_raw, do_echo=False)


@discover.command()
@click.pass_context
async def list(ctx: click.Context) -> DeviceDict:
    """List devices in the network in a table using broadcast discovery."""
    devices_by_host: dict[str, Device] = {}
    discovery_info_by_host: dict[str, dict[str, Any]] = {}
    raw_responses_by_host: dict[str, builtins.list[DiscoveredRaw]] = {}
    results_by_host: dict[str, str] = {}

    def capture_raw(response: DiscoveredRaw) -> None:
        """Retain discovery source metadata for the final list row."""
        raw_responses_by_host.setdefault(response["meta"]["ip"], []).append(response)

    async def print_discovered(dev: Device):
        devices_by_host[dev.host] = dev
        try:
            await dev.update()
        except TimeoutError:
            results_by_host[dev.host] = "Timed out"
        except (AuthenticationError, UnsupportedDeviceError):
            raise
        except Exception as ex:  # pragma: no cover - defensive CLI reporting
            results_by_host[dev.host] = f"Error: {ex}"
        else:
            results_by_host[dev.host] = dev.alias or "-"

    async def print_unsupported(unsupported_exception: UnsupportedDeviceError):
        host = unsupported_exception.host or "unknown"
        if unsupported_exception.discovery_result:
            discovery_info_by_host[host] = unsupported_exception.discovery_result
        if isinstance(unsupported_exception, UnsupportedAuthenticationError):
            source = unsupported_exception.onboarding_source or "unknown"
            results_by_host[host] = f"Unsupported authentication ({source})"
        else:
            results_by_host[host] = "Unsupported device"

    async def print_authentication_error(
        authentication_error: DiscoveryAuthenticationError,
    ) -> None:
        host = authentication_error.host or "unknown"
        if authentication_error.discovery_result:
            discovery_info_by_host[host] = authentication_error.discovery_result
        results_by_host[host] = "Authentication failed"

    echo(
        f"{'HOST':<15} {'MODEL':<9} {'DEVICE FAMILY':<20} {'ENCRYPT':<7} "
        f"{'HTTPS':<5} {'LV':<3} {'KV':<3} {'SOURCE':<9} {'ALIAS / RESULT'}"
    )
    discovered = await _discover(
        ctx,
        print_discovered=print_discovered,
        print_unsupported=print_unsupported,
        print_authentication_error=print_authentication_error,
        print_raw=capture_raw,
        do_echo=False,
    )

    display_hosts = (
        set(devices_by_host)
        | set(discovery_info_by_host)
        | set(raw_responses_by_host)
        | set(results_by_host)
    )
    for host in sorted(display_hosts):
        device = devices_by_host.get(host)
        responses = raw_responses_by_host.get(host, [])
        selected_response = select_discovery_response(responses) if responses else None
        discovery_info = (
            selected_response["discovery_response"]
            if selected_response is not None
            else discovery_info_by_host.get(host)
        )
        info = _get_discovery_list_info(
            host,
            device=device,
            discovery_info=discovery_info,
        )
        echo(
            _format_discovery_list_row(
                info,
                source=_format_discovery_source(selected_response),
                result=results_by_host.get(host, "-"),
            )
        )
    return discovered


async def _discover(
    ctx: click.Context,
    *,
    print_discovered: OnDiscoveredCallable | None = None,
    print_unsupported: OnUnsupportedCallable | None = None,
    print_authentication_error: OnAuthenticationErrorCallable | None = None,
    print_raw: OnDiscoveredRawCallable | None = None,
    do_echo=True,
) -> DeviceDict:
    params = ctx.find_root().params
    target = params["target"]
    username = params["username"]
    password = params["password"]
    credentials_hash = params["credentials_hash"]
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
            credentials_hash=credentials_hash,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
            on_discovered=print_discovered,
            on_unsupported=print_unsupported,
            on_authentication_error=print_authentication_error,
            on_discovered_raw=print_raw,
        )
        if dev:
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
        on_authentication_error=print_authentication_error,
        port=port,
        timeout=timeout,
        credentials=credentials,
        credentials_hash=credentials_hash,
        on_discovered_raw=print_raw,
    )

    return discovered_devices


@discover.command()
@click.pass_context
async def config(ctx: click.Context) -> DeviceDict:
    """Show the authoritative connection config for a device.

    Uses targeted discovery first and falls back to direct connection probing
    when no discovery response is received.
    """
    params = ctx.find_root().params
    username = params["username"]
    password = params["password"]
    credentials_hash = params["credentials_hash"]
    timeout = params["timeout"]
    discovery_timeout = params["discovery_timeout"]
    host = params["host"]
    port = params["port"]

    if not host:
        error("--host option must be supplied to discover config")

    credentials = Credentials(username, password) if username and password else None

    raw_responses: builtins.list[DiscoveredRaw] = []

    echo(f"Discovering device {host} for {discovery_timeout} seconds")
    device: Device | None = None
    discovery_error: KasaException | None = None
    try:
        device = await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
            credentials_hash=credentials_hash,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
            on_discovered_raw=raw_responses.append,
        )
    except KasaException as ex:
        discovery_error = ex

    if raw_responses:
        response = select_discovery_response(raw_responses)
        if connection_type := _connection_parameters_from_discovery(response, device):
            meta = response["meta"]
            echo(
                f"Using {_format_discovery_source(response)} discovery response "
                f"from {meta['ip']}"
            )
            echo("CLI options for the discovered connection are:")
            echo(_format_connection_options(connection_type))
            return {host: device} if device is not None else {}
        error(
            "Unable to determine a connection configuration from the "
            f"{_format_discovery_source(response)} discovery response"
        )

    if device is not None:
        # A device without a raw callback is unexpected, but its normalized
        # config is still more authoritative than speculative direct probing.
        echo("CLI options for the discovered connection are:")
        echo(_format_connection_options(device.config.connection_type))
        return {host: device}

    if discovery_error is not None:
        echo(f"Discovery did not provide a usable connection config: {discovery_error}")
    else:
        echo("Discovery did not provide a usable connection config")
    echo("Trying direct connection routes instead")

    host_port = host + (f":{port}" if port else "")

    def on_attempt(connect_attempt: ConnectAttempt, success: bool) -> None:
        prot = connect_attempt.protocol
        tran = connect_attempt.transport
        dev = connect_attempt.device
        https = connect_attempt.https
        key_str = (
            f"{prot.__name__} + {tran.__name__} + {dev.__name__}"
            f" + {'https' if https else 'http'}"
        )
        connection_type = connect_attempt.connection_type
        key_str += (
            f" [{connection_type.device_family.value}, "
            f"{connection_type.encryption_type.value}, "
            f"lv={connection_type.login_version or '-'}, "
            f"kv={connection_type.klap_version or '-'}]"
        )
        result = "succeeded" if success else "failed"
        msg = f"Attempt to connect to {host_port} with {key_str} {result}"
        echo(msg)

    dev = await Discover.try_connect_all(
        host,
        credentials=credentials,
        credentials_hash=credentials_hash,
        timeout=timeout,
        port=port,
        on_attempt=on_attempt,
    )
    if dev:
        echo("Managed to connect using direct probing, CLI options are:")
        echo(_format_connection_options(dev.config.connection_type))
        return {host: dev}
    else:
        error(f"Unable to connect to {host}")


def _echo_dictionary(discovery_info: dict) -> None:
    echo("\t[bold]== Discovery information ==[/bold]")
    for key, value in discovery_info.items():
        key_name = " ".join(x.capitalize() or "_" for x in key.split("_"))
        key_name_and_spaces = "{:<15}".format(key_name + ":")
        echo(f"\t{key_name_and_spaces}{value}")


def echo_discovery_info(discovery_info: dict) -> None:
    """Print decoded discovery information for CLI commands."""
    # We don't have discovery info when all connection params are passed manually
    if discovery_info is None:
        return

    if sysinfo := extract_sys_info(discovery_info):
        _echo_dictionary(sysinfo)
        return

    tdp_info = discovery_info.get("result", discovery_info)
    if not isinstance(tdp_info, dict):
        _echo_dictionary(discovery_info)
        return
    try:
        dr = DiscoveryResult.from_dict(tdp_info)
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
        _conditional_echo("KLAP version", mgt_encrypt_schm.new_klap)
    _conditional_echo("Encrypt info", pf(dr.encrypt_info) if dr.encrypt_info else None)
    _conditional_echo("Decrypted", pf(dr.decrypted_data) if dr.decrypted_data else None)


async def find_dev_from_alias(
    alias: str,
    credentials: Credentials | None,
    credentials_hash: str | None = None,
    target: str = "255.255.255.255",
    timeout: int = 5,
    discovery_timeout: int = 5,
    port: int | None = None,
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
                credentials_hash=credentials_hash,
                discovery_timeout=discovery_timeout,
                port=port,
                on_discovered=on_discovered,
            )
            if found_event.is_set():
                break
        found_event.set()

    asyncio.create_task(do_discover())
    await found_event.wait()
    return found_device[0] if found_device else None
