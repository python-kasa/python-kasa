"""python-kasa cli tool."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

import asyncclick as click

from kasa import (
    Credentials,
    Device,
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
    Discover,
)
from kasa.cli.common import (
    SKIP_UPDATE_COMMANDS,
    CatchAllExceptions,
    echo,
    error,
    json_formatter_cb,
)
from kasa.cli.lazygroup import LazyGroup
from kasa.iot import (
    IotBulb,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from kasa.smart import SmartDevice

TYPE_TO_CLASS = {
    "plug": IotPlug,
    "switch": IotWallSwitch,
    "bulb": IotBulb,
    "dimmer": IotDimmer,
    "strip": IotStrip,
    "lightstrip": IotLightStrip,
    "iot.plug": IotPlug,
    "iot.switch": IotWallSwitch,
    "iot.bulb": IotBulb,
    "iot.dimmer": IotDimmer,
    "iot.strip": IotStrip,
    "iot.lightstrip": IotLightStrip,
    "smart.plug": SmartDevice,
    "smart.bulb": SmartDevice,
}

ENCRYPT_TYPES = [encrypt_type.value for encrypt_type in DeviceEncryptionType]

DEVICE_FAMILY_TYPES = [device_family_type.value for device_family_type in DeviceFamily]


@click.group(
    invoke_without_command=True,
    cls=CatchAllExceptions(LazyGroup),
    lazy_subcommands={
        "discover": "kasa.cli.discover.discover",
        "wifi": "kasa.cli.wifi.wifi",
        "feature": "kasa.cli.feature.feature",
        "time": "kasa.cli.time.time",
        "schedule": "kasa.cli.schedule.schedule",
        # device
        "state": "kasa.cli.device.state",
        "on": "kasa.cli.device.on",
        "off": "kasa.cli.device.off",
        "toggle": "kasa.cli.device.toggle",
        "led": "kasa.cli.device.led",
        "alias": "kasa.cli.device.alias",
        "reboot": "kasa.cli.device.reboot",
        "update_credentials": "kasa.cli.device.update_credentials",
        "sysinfo": "kasa.cli.device.sysinfo",
        # light
        "presets": "kasa.cli.light.presets",
        "brightness": "kasa.cli.light.brightness",
        "hsv": "kasa.cli.light.hsv",
        "temperature": "kasa.cli.light.temperature",
        "effect": "kasa.cli.light.effect",
        # util
        "shell": "kasa.cli.util.shell",
        "command": "kasa.cli.util.cmd_command",
        "raw_command": "kasa.cli.util.raw_command",
    },
    result_callback=json_formatter_cb,
)
@click.option(
    "--host",
    envvar="KASA_HOST",
    required=False,
    help="The host name or IP address of the device to connect to.",
)
@click.option(
    "--port",
    envvar="KASA_PORT",
    required=False,
    type=int,
    help="The port of the device to connect to.",
)
@click.option(
    "--alias",
    envvar="KASA_NAME",
    required=False,
    help="The device name, or alias, of the device to connect to.",
)
@click.option(
    "--target",
    envvar="KASA_TARGET",
    default="255.255.255.255",
    required=False,
    show_default=True,
    help="The broadcast address to be used for discovery.",
)
@click.option(
    "-v",
    "--verbose",
    envvar="KASA_VERBOSE",
    required=False,
    default=False,
    is_flag=True,
    help="Be more verbose on output",
)
@click.option(
    "-d",
    "--debug",
    envvar="KASA_DEBUG",
    default=False,
    is_flag=True,
    help="Print debug output",
)
@click.option(
    "--type",
    envvar="KASA_TYPE",
    default=None,
    type=click.Choice(list(TYPE_TO_CLASS), case_sensitive=False),
)
@click.option(
    "--json/--no-json",
    envvar="KASA_JSON",
    default=False,
    is_flag=True,
    help="Output raw device response as JSON.",
)
@click.option(
    "-e",
    "--encrypt-type",
    envvar="KASA_ENCRYPT_TYPE",
    default=None,
    type=click.Choice(ENCRYPT_TYPES, case_sensitive=False),
)
@click.option(
    "--device-family",
    envvar="KASA_DEVICE_FAMILY",
    default="SMART.TAPOPLUG",
    type=click.Choice(DEVICE_FAMILY_TYPES, case_sensitive=False),
)
@click.option(
    "-lv",
    "--login-version",
    envvar="KASA_LOGIN_VERSION",
    default=2,
    type=int,
)
@click.option(
    "--timeout",
    envvar="KASA_TIMEOUT",
    default=5,
    required=False,
    show_default=True,
    help="Timeout for device communications.",
)
@click.option(
    "--discovery-timeout",
    envvar="KASA_DISCOVERY_TIMEOUT",
    default=5,
    required=False,
    show_default=True,
    help="Timeout for discovery.",
)
@click.option(
    "--username",
    default=None,
    required=False,
    envvar="KASA_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    default=None,
    required=False,
    envvar="KASA_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.option(
    "--credentials-hash",
    default=None,
    required=False,
    envvar="KASA_CREDENTIALS_HASH",
    help="Hashed credentials used to authenticate to the device.",
)
@click.version_option(package_name="python-kasa")
@click.pass_context
async def cli(
    ctx,
    host,
    port,
    alias,
    target,
    verbose,
    debug,
    type,
    encrypt_type,
    device_family,
    login_version,
    json,
    timeout,
    discovery_timeout,
    username,
    password,
    credentials_hash,
):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    # no need to perform any checks if we are just displaying the help
    if "--help" in sys.argv:
        # Context object is required to avoid crashing on sub-groups
        ctx.obj = object()
        return

    logging_config: dict[str, Any] = {
        "level": logging.DEBUG if debug > 0 else logging.INFO
    }
    try:
        from rich.logging import RichHandler

        rich_config = {
            "show_time": False,
        }
        logging_config["handlers"] = [RichHandler(**rich_config)]
        logging_config["format"] = "%(message)s"
    except ImportError:
        pass

    # The configuration should be converted to use dictConfig,
    # but this keeps mypy happy for now
    logging.basicConfig(**logging_config)  # type: ignore

    if ctx.invoked_subcommand == "discover":
        return

    if alias is not None and host is not None:
        raise click.BadOptionUsage("alias", "Use either --alias or --host, not both.")

    if alias is not None and host is None:
        echo(f"Alias is given, using discovery to find host {alias}")

        from kasa.cli.discover import find_host_from_alias

        host = await find_host_from_alias(alias=alias, target=target)
        if host:
            echo(f"Found hostname is {host}")
        else:
            echo(f"No device with name {alias} found")
            return

    if bool(password) != bool(username):
        raise click.BadOptionUsage(
            "username", "Using authentication requires both --username and --password"
        )

    if username:
        credentials = Credentials(username=username, password=password)
    else:
        credentials = None

    if host is None:
        if ctx.invoked_subcommand and ctx.invoked_subcommand != "discover":
            error("Only discover is available without --host or --alias")

        echo("No host name given, trying discovery..")
        from kasa.cli.discover import discover

        return await ctx.invoke(discover)

    device_updated = False
    if type is not None:
        config = DeviceConfig(host=host, port_override=port, timeout=timeout)
        dev = TYPE_TO_CLASS[type](host, config=config)
    elif device_family and encrypt_type:
        ctype = DeviceConnectionParameters(
            DeviceFamily(device_family),
            DeviceEncryptionType(encrypt_type),
            login_version,
        )
        config = DeviceConfig(
            host=host,
            port_override=port,
            credentials=credentials,
            credentials_hash=credentials_hash,
            timeout=timeout,
            connection_type=ctype,
        )
        dev = await Device.connect(config=config)
        device_updated = True
    else:
        dev = await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
        )

    # Skip update on specific commands, or if device factory,
    # that performs an update was used for the device.
    if ctx.invoked_subcommand not in SKIP_UPDATE_COMMANDS and not device_updated:
        await dev.update()

    @asynccontextmanager
    async def async_wrapped_device(device: Device):
        try:
            yield device
        finally:
            await device.disconnect()

    ctx.obj = await ctx.with_async_resource(async_wrapped_device(dev))

    if ctx.invoked_subcommand is None:
        from kasa.cli.device import state

        return await ctx.invoke(state)


if __name__ == "__main__":
    cli()
