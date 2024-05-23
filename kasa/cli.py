"""python-kasa cli tool."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from functools import singledispatch, wraps
from pprint import pformat as pf
from typing import Any, cast

import asyncclick as click
from pydantic.v1 import ValidationError

from kasa import (
    AuthenticationError,
    ConnectionType,
    Credentials,
    Device,
    DeviceConfig,
    DeviceFamilyType,
    Discover,
    EncryptType,
    Feature,
    KasaException,
    Module,
    UnsupportedDeviceError,
)
from kasa.discover import DiscoveryResult
from kasa.iot import (
    IotBulb,
    IotDevice,
    IotDimmer,
    IotLightStrip,
    IotPlug,
    IotStrip,
    IotWallSwitch,
)
from kasa.iot.modules import Usage
from kasa.smart import SmartDevice

try:
    from rich import print as _do_echo
except ImportError:
    # Strip out rich formatting if rich is not installed
    # but only lower case tags to avoid stripping out
    # raw data from the device that is printed from
    # the device state.
    rich_formatting = re.compile(r"\[/?[a-z]+]")

    def _strip_rich_formatting(echo_func):
        """Strip rich formatting from messages."""

        @wraps(echo_func)
        def wrapper(message=None, *args, **kwargs):
            if message is not None:
                message = rich_formatting.sub("", message)
            echo_func(message, *args, **kwargs)

        return wrapper

    _do_echo = _strip_rich_formatting(click.echo)

# echo is set to _do_echo so that it can be reset to _do_echo later after
# --json has set it to _nop_echo
echo = _do_echo


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

ENCRYPT_TYPES = [encrypt_type.value for encrypt_type in EncryptType]

DEVICE_FAMILY_TYPES = [
    device_family_type.value for device_family_type in DeviceFamilyType
]

# Block list of commands which require no update
SKIP_UPDATE_COMMANDS = ["wifi", "raw-command", "command"]

click.anyio_backend = "asyncio"

pass_dev = click.make_pass_decorator(Device)


def CatchAllExceptions(cls):
    """Capture all exceptions and prints them nicely.

    Idea from https://stackoverflow.com/a/44347763 and
    https://stackoverflow.com/questions/52213375
    """

    def _handle_exception(debug, exc):
        if isinstance(exc, click.ClickException):
            raise
        echo(f"Raised error: {exc}")
        if debug:
            raise
        echo("Run with --debug enabled to see stacktrace")
        sys.exit(1)

    class _CommandCls(cls):
        _debug = False

        async def make_context(self, info_name, args, parent=None, **extra):
            self._debug = any(
                [arg for arg in args if arg in ["--debug", "-d", "--verbose", "-v"]]
            )
            try:
                return await super().make_context(
                    info_name, args, parent=parent, **extra
                )
            except Exception as exc:
                _handle_exception(self._debug, exc)

        async def invoke(self, ctx):
            try:
                return await super().invoke(ctx)
            except Exception as exc:
                _handle_exception(self._debug, exc)

    return _CommandCls


def json_formatter_cb(result, **kwargs):
    """Format and output the result as JSON, if requested."""
    if not kwargs.get("json"):
        return

    @singledispatch
    def to_serializable(val):
        """Regular obj-to-string for json serialization.

        The singledispatch trick is from hynek: https://hynek.me/articles/serialization/
        """
        return str(val)

    @to_serializable.register(Device)
    def _device_to_serializable(val: Device):
        """Serialize smart device data, just using the last update raw payload."""
        return val.internal_state

    json_content = json.dumps(result, indent=4, default=to_serializable)
    print(json_content)


@click.group(
    invoke_without_command=True,
    cls=CatchAllExceptions(click.Group),
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
    "--encrypt-type",
    envvar="KASA_ENCRYPT_TYPE",
    default=None,
    type=click.Choice(ENCRYPT_TYPES, case_sensitive=False),
)
@click.option(
    "--device-family",
    envvar="KASA_DEVICE_FAMILY",
    default=None,
    type=click.Choice(DEVICE_FAMILY_TYPES, case_sensitive=False),
)
@click.option(
    "--login-version",
    envvar="KASA_LOGIN_VERSION",
    default=None,
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

    # If JSON output is requested, disable echo
    global echo
    if json:

        def _nop_echo(*args, **kwargs):
            pass

        echo = _nop_echo
    else:
        # Set back to default is required if running tests with CliRunner
        global _do_echo
        echo = _do_echo

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
        echo("No host name given, trying discovery..")
        return await ctx.invoke(discover)

    if type is not None:
        dev = TYPE_TO_CLASS[type](host)
    elif device_family and encrypt_type:
        ctype = ConnectionType(
            DeviceFamilyType(device_family),
            EncryptType(encrypt_type),
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
    else:
        echo(
            "No --type or --device-family and --encrypt-type defined, "
            + f"discovering for {discovery_timeout} seconds.."
        )
        dev = await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
            timeout=timeout,
            discovery_timeout=discovery_timeout,
        )

    # Skip update on specific commands, or if device factory,
    # that performs an update was used for the device.
    if ctx.invoked_subcommand not in SKIP_UPDATE_COMMANDS and not device_family:
        await dev.update()

    @asynccontextmanager
    async def async_wrapped_device(device: Device):
        try:
            yield device
        finally:
            await device.disconnect()

    ctx.obj = await ctx.with_async_resource(async_wrapped_device(dev))

    if ctx.invoked_subcommand is None:
        return await ctx.invoke(state)


@cli.group()
@pass_dev
def wifi(dev):
    """Commands to control wifi settings."""


@wifi.command()
@pass_dev
async def scan(dev):
    """Scan for available wifi networks."""
    echo("Scanning for wifi networks, wait a second..")
    devs = await dev.wifi_scan()
    echo(f"Found {len(devs)} wifi networks!")
    for dev in devs:
        echo(f"\t {dev}")

    return devs


@wifi.command()
@click.argument("ssid")
@click.option("--keytype", prompt=True)
@click.option("--password", prompt=True, hide_input=True)
@pass_dev
async def join(dev: Device, ssid: str, password: str, keytype: str):
    """Join the given wifi network."""
    echo(f"Asking the device to connect to {ssid}..")
    res = await dev.wifi_join(ssid, password, keytype=keytype)
    echo(
        f"Response: {res} - if the device is not able to join the network, "
        f"it will revert back to its previous state."
    )

    return res


@cli.command()
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


@cli.command()
@pass_dev
async def sysinfo(dev):
    """Print out full system information."""
    echo("== System info ==")
    echo(pf(dev.sys_info))
    return dev.sys_info


def _echo_features(
    features: dict[str, Feature],
    title: str,
    category: Feature.Category | None = None,
    verbose: bool = False,
    indent: str = "\t",
):
    """Print out a listing of features and their values."""
    if category is not None:
        features = {
            id_: feat for id_, feat in features.items() if feat.category == category
        }

    if not features:
        return
    echo(f"[bold]{title}[/bold]")
    for _, feat in features.items():
        try:
            echo(f"{indent}{feat}")
            if verbose:
                echo(f"{indent}\tType: {feat.type}")
                echo(f"{indent}\tCategory: {feat.category}")
                echo(f"{indent}\tIcon: {feat.icon}")
        except Exception as ex:
            echo(f"{indent}{feat.name} ({feat.id}): [red]got exception ({ex})[/red]")


def _echo_all_features(features, *, verbose=False, title_prefix=None):
    """Print out all features by category."""
    if title_prefix is not None:
        echo(f"[bold]\n\t == {title_prefix} ==[/bold]")
    _echo_features(
        features,
        title="\n\t== Primary features ==",
        category=Feature.Category.Primary,
        verbose=verbose,
    )
    _echo_features(
        features,
        title="\n\t== Information ==",
        category=Feature.Category.Info,
        verbose=verbose,
    )
    _echo_features(
        features,
        title="\n\t== Configuration ==",
        category=Feature.Category.Config,
        verbose=verbose,
    )
    _echo_features(
        features,
        title="\n\t== Debug ==",
        category=Feature.Category.Debug,
        verbose=verbose,
    )


@cli.command()
@pass_dev
@click.pass_context
async def state(ctx, dev: Device):
    """Print out device state and versions."""
    verbose = ctx.parent.params.get("verbose", False) if ctx.parent else False

    echo(f"[bold]== {dev.alias} - {dev.model} ==[/bold]")
    echo(f"\tHost: {dev.host}")
    echo(f"\tPort: {dev.port}")
    echo(f"\tDevice state: {dev.is_on}")
    if dev.children:
        echo("\t== Children ==")
        for child in dev.children:
            _echo_all_features(
                child.features,
                title_prefix=f"{child.alias} ({child.model}, {child.device_type})",
                verbose=verbose,
            )

        echo()

    echo("\t[bold]== Generic information ==[/bold]")
    echo(f"\tTime:         {dev.time} (tz: {dev.timezone}")
    echo(f"\tHardware:     {dev.hw_info['hw_ver']}")
    echo(f"\tSoftware:     {dev.hw_info['sw_ver']}")
    echo(f"\tMAC (rssi):   {dev.mac} ({dev.rssi})")
    echo(f"\tLocation:     {dev.location}")

    _echo_all_features(dev.features, verbose=verbose)

    echo("\n\t[bold]== Modules ==[/bold]")
    for module in dev.modules.values():
        echo(f"\t[green]+ {module}[/green]")

    if verbose:
        echo("\n\t[bold]== Protocol information ==[/bold]")
        echo(f"\tCredentials hash:  {dev.credentials_hash}")
        echo()
        _echo_discovery_info(dev._discovery_info)
    return dev.internal_state


@cli.command()
@pass_dev
@click.argument("new_alias", required=False, default=None)
@click.option("--index", type=int)
async def alias(dev, new_alias, index):
    """Get or set the device (or plug) alias."""
    if index is not None:
        if not dev.is_strip:
            echo("Index can only used for power strips!")
            return
        dev = dev.get_plug_by_index(index)

    if new_alias is not None:
        echo(f"Setting alias to {new_alias}")
        res = await dev.set_alias(new_alias)
        return res

    echo(f"Alias: {dev.alias}")
    if dev.is_strip:
        for plug in dev.children:
            echo(f"  * {plug.alias}")

    return dev.alias


@cli.command()
@pass_dev
@click.pass_context
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(ctx, dev: Device, module, command, parameters):
    """Run a raw command on the device."""
    logging.warning("Deprecated, use 'kasa command --module %s %s'", module, command)
    return await ctx.forward(cmd_command)


@cli.command(name="command")
@pass_dev
@click.option("--module", required=False, help="Module for IOT protocol.")
@click.option("--child", required=False, help="Child ID for controlling sub-devices")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def cmd_command(dev: Device, module, child, command, parameters):
    """Run a raw command on the device."""
    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    if child:
        # The way child devices are accessed requires a ChildDevice to
        # wrap the communications. Doing this properly would require creating
        # a common interfaces for both IOT and SMART child devices.
        # As a stop-gap solution, we perform an update instead.
        await dev.update()
        dev = dev.get_child_device(child)

    if isinstance(dev, IotDevice):
        res = await dev._query_helper(module, command, parameters)
    elif isinstance(dev, SmartDevice):
        res = await dev._query_helper(command, parameters)
    else:
        raise KasaException("Unexpected device type %s.", dev)
    echo(json.dumps(res))
    return res


@cli.command()
@pass_dev
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def emeter(dev: Device, index: int, name: str, year, month, erase):
    """Query emeter for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    if index is not None or name is not None:
        if not dev.is_strip:
            echo("Index and name are only for power strips!")
            return

        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    echo("[bold]== Emeter ==[/bold]")
    if not dev.has_emeter:
        echo("Device has no emeter")
        return

    if (year or month or erase) and not isinstance(dev, IotDevice):
        echo("Device has no historical statistics")
        return
    else:
        dev = cast(IotDevice, dev)

    if erase:
        echo("Erasing emeter statistics..")
        return await dev.erase_emeter_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (kWh)")
        usage_data = await dev.get_emeter_monthly(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (kWh)")
        usage_data = await dev.get_emeter_daily(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        if index is not None or name is not None:
            emeter_status = await dev.get_emeter_realtime()
        else:
            emeter_status = dev.emeter_realtime

        echo("Current: %s A" % emeter_status["current"])
        echo("Voltage: %s V" % emeter_status["voltage"])
        echo("Power: %s W" % emeter_status["power"])
        echo("Total consumption: %s kWh" % emeter_status["total"])

        echo("Today: %s kWh" % dev.emeter_today)
        echo("This month: %s kWh" % dev.emeter_this_month)

        return emeter_status

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def usage(dev: Device, year, month, erase):
    """Query usage for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Usage ==[/bold]")
    usage = cast(Usage, dev.modules["usage"])

    if erase:
        echo("Erasing usage statistics..")
        return await usage.erase_stats()

    if year:
        echo(f"== For year {year.year} ==")
        echo("Month, usage (minutes)")
        usage_data = await usage.get_monthstat(year=year.year)
    elif month:
        echo(f"== For month {month.month} of {month.year} ==")
        echo("Day, usage (minutes)")
        usage_data = await usage.get_daystat(year=month.year, month=month.month)
    else:
        # Call with no argument outputs summary data and returns
        echo("Today: %s minutes" % usage.usage_today)
        echo("This month: %s minutes" % usage.usage_this_month)

        return usage

    # output any detailed usage data
    for index, usage in usage_data.items():
        echo(f"{index}, {usage}")

    return usage_data


@cli.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def brightness(dev: Device, brightness: int, transition: int):
    """Get or set brightness."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_dimmable:
        echo("This device does not support brightness.")
        return

    if brightness is None:
        echo(f"Brightness: {light.brightness}")
        return light.brightness
    else:
        echo(f"Setting brightness to {brightness}")
        return await light.set_brightness(brightness, transition=transition)


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@click.option("--transition", type=int, required=False)
@pass_dev
async def temperature(dev: Device, temperature: int, transition: int):
    """Get or set color temperature."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_variable_color_temp:
        echo("Device does not support color temperature")
        return

    if temperature is None:
        echo(f"Color temperature: {light.color_temp}")
        valid_temperature_range = light.valid_temperature_range
        if valid_temperature_range != (0, 0):
            echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
        return light.valid_temperature_range
    else:
        echo(f"Setting color temperature to {temperature}")
        return await light.set_color_temp(temperature, transition=transition)


@cli.command()
@click.argument("effect", type=click.STRING, default=None, required=False)
@click.pass_context
@pass_dev
async def effect(dev: Device, ctx, effect):
    """Set an effect."""
    if not (light_effect := dev.modules.get(Module.LightEffect)):
        echo("Device does not support effects")
        return
    if effect is None:
        echo(
            f"Light effect: {light_effect.effect}\n"
            + f"Available Effects: {light_effect.effect_list}"
        )
        return light_effect.effect

    if effect not in light_effect.effect_list:
        raise click.BadArgumentUsage(
            f"Effect must be one of: {light_effect.effect_list}", ctx
        )

    echo(f"Setting Effect: {effect}")
    return await light_effect.set_effect(effect)


@cli.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
@pass_dev
async def hsv(dev: Device, ctx, h, s, v, transition):
    """Get or set color in HSV."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_color:
        echo("Device does not support colors")
        return

    if h is None and s is None and v is None:
        echo(f"Current HSV: {light.hsv}")
        return light.hsv
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        echo(f"Setting HSV: {h} {s} {v}")
        return await light.set_hsv(h, s, v, transition=transition)


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
async def led(dev: Device, state):
    """Get or set (Plug's) led state."""
    if not (led := dev.modules.get(Module.Led)):
        echo("Device does not support led.")
        return
    if state is not None:
        echo(f"Turning led to {state}")
        return await led.set_led(state)
    else:
        echo(f"LED state: {led.led}")
        return led.led


@cli.command()
@pass_dev
async def time(dev):
    """Get the device time."""
    res = dev.time
    echo(f"Current time: {res}")
    return res


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def on(dev: Device, index: int, name: str, transition: int):
    """Turn the device on."""
    if index is not None or name is not None:
        if not dev.children:
            echo("Index and name are only for devices with children.")
            return

        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    echo(f"Turning on {dev.alias}")
    return await dev.turn_on(transition=transition)


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def off(dev: Device, index: int, name: str, transition: int):
    """Turn the device off."""
    if index is not None or name is not None:
        if not dev.children:
            echo("Index and name are only for devices with children.")
            return

        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    echo(f"Turning off {dev.alias}")
    return await dev.turn_off(transition=transition)


@cli.command()
@click.option("--index", type=int, required=False)
@click.option("--name", type=str, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev
async def toggle(dev: Device, index: int, name: str, transition: int):
    """Toggle the device on/off."""
    if index is not None or name is not None:
        if not dev.children:
            echo("Index and name are only for devices with children.")
            return

        if index is not None:
            dev = dev.get_plug_by_index(index)
        elif name:
            dev = dev.get_plug_by_name(name)

    if dev.is_on:
        echo(f"Turning off {dev.alias}")
        return await dev.turn_off(transition=transition)

    echo(f"Turning on {dev.alias}")
    return await dev.turn_on(transition=transition)


@cli.command()
@click.option("--delay", default=1)
@pass_dev
async def reboot(plug, delay):
    """Reboot the device."""
    echo("Rebooting the device..")
    return await plug.reboot(delay)


@cli.group()
@pass_dev
async def schedule(dev):
    """Scheduling commands."""


@schedule.command(name="list")
@pass_dev
@click.argument("type", default="schedule")
def _schedule_list(dev, type):
    """Return the list of schedule actions for the given type."""
    sched = dev.modules[type]
    for rule in sched.rules:
        print(rule)
    else:
        echo(f"No rules of type {type}")

    return sched.rules


@schedule.command(name="delete")
@pass_dev
@click.option("--id", type=str, required=True)
async def delete_rule(dev, id):
    """Delete rule from device."""
    schedule = dev.modules["schedule"]
    rule_to_delete = next(filter(lambda rule: (rule.id == id), schedule.rules), None)
    if rule_to_delete:
        echo(f"Deleting rule id {id}")
        return await schedule.delete_rule(rule_to_delete)
    else:
        echo(f"No rule with id {id} was found")


@cli.group(invoke_without_command=True)
@click.pass_context
async def presets(ctx):
    """List and modify bulb setting presets."""
    if ctx.invoked_subcommand is None:
        return await ctx.invoke(presets_list)


@presets.command(name="list")
@pass_dev
def presets_list(dev: IotBulb):
    """List presets."""
    if not dev.is_bulb or not isinstance(dev, IotBulb):
        echo("Presets only supported on iot bulbs")
        return

    for preset in dev.presets:
        echo(preset)

    return dev.presets


@presets.command(name="modify")
@click.argument("index", type=int)
@click.option("--brightness", type=int)
@click.option("--hue", type=int)
@click.option("--saturation", type=int)
@click.option("--temperature", type=int)
@pass_dev
async def presets_modify(dev: IotBulb, index, brightness, hue, saturation, temperature):
    """Modify a preset."""
    for preset in dev.presets:
        if preset.index == index:
            break
    else:
        echo(f"No preset found for index {index}")
        return

    if brightness is not None:
        preset.brightness = brightness
    if hue is not None:
        preset.hue = hue
    if saturation is not None:
        preset.saturation = saturation
    if temperature is not None:
        preset.color_temp = temperature

    echo(f"Going to save preset: {preset}")

    return await dev.save_preset(preset)


@cli.command()
@pass_dev
@click.option("--type", type=click.Choice(["soft", "hard"], case_sensitive=False))
@click.option("--last", is_flag=True)
@click.option("--preset", type=int)
async def turn_on_behavior(dev: IotBulb, type, last, preset):
    """Modify bulb turn-on behavior."""
    if not dev.is_bulb or not isinstance(dev, IotBulb):
        echo("Presets only supported on iot bulbs")
        return
    settings = await dev.get_turn_on_behavior()
    echo(f"Current turn on behavior: {settings}")

    # Return if we are not setting the value
    if not type and not last and not preset:
        return settings

    # If we are setting the value, the type has to be specified
    if (last or preset) and type is None:
        echo("To set the behavior, you need to define --type")
        return

    behavior = getattr(settings, type)

    if last:
        echo(f"Going to set {type} to last")
        behavior.preset = None
    elif preset is not None:
        echo(f"Going to set {type} to preset {preset}")
        behavior.preset = preset

    return await dev.set_turn_on_behavior(settings)


@cli.command()
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
        raise NotImplementedError(
            "Credentials can only be updated on authenticated devices."
        )

    click.confirm("Do you really want to replace the existing credentials?", abort=True)

    return await dev.update_credentials(username, password)


@cli.command()
@pass_dev
async def shell(dev: Device):
    """Open interactive shell."""
    echo("Opening shell for %s" % dev)
    from ptpython.repl import embed

    logging.getLogger("parso").setLevel(logging.WARNING)  # prompt parsing
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    loop = asyncio.get_event_loop()
    try:
        await embed(
            globals=globals(),
            locals=locals(),
            return_asyncio_coroutine=True,
            patch_stdout=True,
        )
    except EOFError:
        loop.stop()


@cli.command(name="feature")
@click.argument("name", required=False)
@click.argument("value", required=False)
@click.option("--child", required=False)
@pass_dev
async def feature(dev: Device, child: str, name: str, value):
    """Access and modify features.

    If no *name* is given, lists available features and their values.
    If only *name* is given, the value of named feature is returned.
    If both *name* and *value* are set, the described setting is changed.
    """
    if child is not None:
        echo(f"Targeting child device {child}")
        dev = dev.get_child_device(child)
    if not name:
        _echo_features(dev.features, "\n[bold]== Features ==[/bold]\n", indent="")

        if dev.children:
            for child_dev in dev.children:
                _echo_features(
                    child_dev.features,
                    f"\n[bold]== Child {child_dev.alias} ==\n",
                    indent="",
                )

        return

    if name not in dev.features:
        echo(f"No feature by name '{name}'")
        return

    feat = dev.features[name]

    if value is None:
        unit = f" {feat.unit}" if feat.unit else ""
        echo(f"{feat.name} ({name}): {feat.value}{unit}")
        return feat.value

    value = ast.literal_eval(value)
    echo(f"Changing {name} from {feat.value} to {value}")
    response = await dev.features[name].set_value(value)
    await dev.update()
    echo(f"New state: {feat.value}")

    return response


if __name__ == "__main__":
    cli()
