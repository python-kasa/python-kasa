"""python-kasa cli tool."""
import asyncio
import json
import logging
import re
import sys
from functools import singledispatch, wraps
from pprint import pformat as pf
from typing import Any, Dict, cast

import asyncclick as click

from kasa import (
    Credentials,
    Discover,
    SmartBulb,
    SmartDevice,
    SmartDimmer,
    SmartLightStrip,
    SmartPlug,
    SmartStrip,
)

try:
    from rich import print as _do_echo
except ImportError:

    def _strip_rich_formatting(echo_func):
        """Strip rich formatting from messages."""

        @wraps(echo_func)
        def wrapper(message=None, *args, **kwargs):
            if message is not None:
                message = re.sub(r"\[/?.+?]", "", message)
            echo_func(message, *args, **kwargs)

        return wrapper

    _do_echo = _strip_rich_formatting(click.echo)

# echo is set to _do_echo so that it can be reset to _do_echo later after
# --json has set it to _nop_echo
echo = _do_echo

TYPE_TO_CLASS = {
    "plug": SmartPlug,
    "bulb": SmartBulb,
    "dimmer": SmartDimmer,
    "strip": SmartStrip,
    "lightstrip": SmartLightStrip,
}

click.anyio_backend = "asyncio"

pass_dev = click.make_pass_decorator(SmartDevice)


class ExceptionHandlerGroup(click.Group):
    """Group to capture all exceptions and print them nicely.

    Idea from https://stackoverflow.com/a/44347763
    """

    def __call__(self, *args, **kwargs):
        """Run the coroutine in the event loop and print any exceptions."""
        try:
            asyncio.get_event_loop().run_until_complete(self.main(*args, **kwargs))
        except Exception as ex:
            echo(f"Got error: {ex!r}")


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

    @to_serializable.register(SmartDevice)
    def _device_to_serializable(val: SmartDevice):
        """Serialize smart device data, just using the last update raw payload."""
        return val.internal_state

    json_content = json.dumps(result, indent=4, default=to_serializable)
    print(json_content)


@click.group(
    invoke_without_command=True,
    cls=ExceptionHandlerGroup,
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
@click.option("-d", "--debug", envvar="KASA_DEBUG", default=False, is_flag=True)
@click.option(
    "--type",
    envvar="KASA_TYPE",
    default=None,
    type=click.Choice(list(TYPE_TO_CLASS), case_sensitive=False),
)
@click.option(
    "--json", default=False, is_flag=True, help="Output raw device response as JSON."
)
@click.option(
    "--discovery-timeout",
    envvar="KASA_DISCOVERY_TIMEOUT",
    default=3,
    required=False,
    help="Timeout for discovery.",
)
@click.option(
    "--username",
    default=None,
    required=False,
    envvar="TPLINK_CLOUD_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    default=None,
    required=False,
    envvar="TPLINK_CLOUD_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.version_option(package_name="python-kasa")
@click.pass_context
async def cli(
    ctx,
    host,
    port,
    alias,
    target,
    debug,
    type,
    json,
    discovery_timeout,
    username,
    password,
):
    """A tool for controlling TP-Link smart home devices."""  # noqa
    # no need to perform any checks if we are just displaying the help
    if sys.argv[-1] == "--help":
        # Context object is required to avoid crashing on sub-groups
        ctx.obj = SmartDevice(None)
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

    logging_config: Dict[str, Any] = {
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

    credentials = Credentials(username=username, password=password)

    if host is None:
        echo("No host name given, trying discovery..")
        return await ctx.invoke(discover, timeout=discovery_timeout)

    if type is not None:
        dev = TYPE_TO_CLASS[type](host, credentials=credentials)
    else:
        echo("No --type defined, discovering..")
        dev = await Discover.discover_single(
            host,
            port=port,
            credentials=credentials,
        )

    await dev.update()
    ctx.obj = dev

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
@click.option("--password", prompt=True, hide_input=True)
@click.option("--keytype", default=3)
@pass_dev
async def join(dev: SmartDevice, ssid, password, keytype):
    """Join the given wifi network."""
    echo(f"Asking the device to connect to {ssid}..")
    res = await dev.wifi_join(ssid, password, keytype=keytype)
    echo(
        f"Response: {res} - if the device is not able to join the network, "
        f"it will revert back to its previous state."
    )

    return res


@cli.command()
@click.option("--timeout", default=3, required=False)
@click.option(
    "--show-unsupported",
    envvar="KASA_SHOW_UNSUPPORTED",
    required=False,
    default=False,
    is_flag=True,
    help="Print out discovered unsupported devices",
)
@click.pass_context
async def discover(ctx, timeout, show_unsupported):
    """Discover devices in the network."""
    target = ctx.parent.params["target"]
    username = ctx.parent.params["username"]
    password = ctx.parent.params["password"]

    credentials = Credentials(username, password)

    sem = asyncio.Semaphore()
    discovered = dict()
    unsupported = []

    async def print_unsupported(data: Dict):
        unsupported.append(data)
        if show_unsupported:
            echo(f"Found unsupported device (tapo/unknown encryption): {data}")
            echo()

    echo(f"Discovering devices on {target} for {timeout} seconds")

    async def print_discovered(dev: SmartDevice):
        await dev.update()
        async with sem:
            discovered[dev.host] = dev.internal_state
            ctx.obj = dev
            await ctx.invoke(state)
            echo()

    await Discover.discover(
        target=target,
        timeout=timeout,
        on_discovered=print_discovered,
        on_unsupported=print_unsupported,
        credentials=credentials,
    )

    echo(f"Found {len(discovered)} devices")
    if unsupported:
        echo(
            f"Found {len(unsupported)} unsupported devices"
            + (
                ""
                if show_unsupported
                else ", to show them use: kasa discover --show-unsupported"
            )
        )

    return discovered


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


@cli.command()
@pass_dev
async def state(dev: SmartDevice):
    """Print out device state and versions."""
    echo(f"[bold]== {dev.alias} - {dev.model} ==[/bold]")
    echo(f"\tHost: {dev.host}")
    echo(f"\tPort: {dev.port}")
    echo(f"\tDevice state: {dev.is_on}")
    if dev.is_strip:
        echo("\t[bold]== Plugs ==[/bold]")
        for plug in dev.children:  # type: ignore
            echo(f"\t* Socket '{plug.alias}' state: {plug.is_on} since {plug.on_since}")
        echo()

    echo("\t[bold]== Generic information ==[/bold]")
    echo(f"\tTime:         {dev.time} (tz: {dev.timezone}")
    echo(f"\tHardware:     {dev.hw_info['hw_ver']}")
    echo(f"\tSoftware:     {dev.hw_info['sw_ver']}")
    echo(f"\tMAC (rssi):   {dev.mac} ({dev.rssi})")
    echo(f"\tLocation:     {dev.location}")

    echo("\n\t[bold]== Device specific information ==[/bold]")
    for info_name, info_data in dev.state_information.items():
        if isinstance(info_data, list):
            echo(f"\t{info_name}:")
            for item in info_data:
                echo(f"\t\t{item}")
        else:
            echo(f"\t{info_name}: {info_data}")

    if dev.has_emeter:
        echo("\n\t[bold]== Current State ==[/bold]")
        emeter_status = dev.emeter_realtime
        echo(f"\t{emeter_status}")

    echo("\n\t[bold]== Modules ==[/bold]")
    for module in dev.modules.values():
        if module.is_supported:
            echo(f"\t[green]+ {module}[/green]")
        else:
            echo(f"\t[red]- {module}[/red]")

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
        dev = cast(SmartStrip, dev)
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
@click.argument("module")
@click.argument("command")
@click.argument("parameters", default=None, required=False)
async def raw_command(dev: SmartDevice, module, command, parameters):
    """Run a raw command on the device."""
    import ast

    if parameters is not None:
        parameters = ast.literal_eval(parameters)

    res = await dev._query_helper(module, command, parameters)
    echo(json.dumps(res))
    return res


@cli.command()
@pass_dev
@click.option("--year", type=click.DateTime(["%Y"]), default=None, required=False)
@click.option("--month", type=click.DateTime(["%Y-%m"]), default=None, required=False)
@click.option("--erase", is_flag=True)
async def emeter(dev: SmartDevice, year, month, erase):
    """Query emeter for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Emeter ==[/bold]")
    if not dev.has_emeter:
        echo("Device has no emeter")
        return

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
async def usage(dev: SmartDevice, year, month, erase):
    """Query usage for historical consumption.

    Daily and monthly data provided in CSV format.
    """
    echo("[bold]== Usage ==[/bold]")
    usage = dev.modules["usage"]

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
async def brightness(dev: SmartBulb, brightness: int, transition: int):
    """Get or set brightness."""
    if not dev.is_dimmable:
        echo("This device does not support brightness.")
        return

    if brightness is None:
        echo(f"Brightness: {dev.brightness}")
        return dev.brightness
    else:
        echo(f"Setting brightness to {brightness}")
        return await dev.set_brightness(brightness, transition=transition)


@cli.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@click.option("--transition", type=int, required=False)
@pass_dev
async def temperature(dev: SmartBulb, temperature: int, transition: int):
    """Get or set color temperature."""
    if not dev.is_variable_color_temp:
        echo("Device does not support color temperature")
        return

    if temperature is None:
        echo(f"Color temperature: {dev.color_temp}")
        valid_temperature_range = dev.valid_temperature_range
        if valid_temperature_range != (0, 0):
            echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
        return dev.valid_temperature_range
    else:
        echo(f"Setting color temperature to {temperature}")
        return await dev.set_color_temp(temperature, transition=transition)


@cli.command()
@click.argument("effect", type=click.STRING, default=None, required=False)
@click.pass_context
@pass_dev
async def effect(dev, ctx, effect):
    """Set an effect."""
    if not dev.has_effects:
        echo("Device does not support effects")
        return
    if effect is None:
        raise click.BadArgumentUsage(
            f"Setting an effect requires a named built-in effect: {dev.effect_list}",
            ctx,
        )
    if effect not in dev.effect_list:
        raise click.BadArgumentUsage(f"Effect must be one of: {dev.effect_list}", ctx)

    echo(f"Setting Effect: {effect}")
    return await dev.set_effect(effect)


@cli.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
@pass_dev
async def hsv(dev, ctx, h, s, v, transition):
    """Get or set color in HSV."""
    if not dev.is_color:
        echo("Device does not support colors")
        return

    if h is None or s is None or v is None:
        echo(f"Current HSV: {dev.hsv}")
        return dev.hsv
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        echo(f"Setting HSV: {h} {s} {v}")
        return await dev.set_hsv(h, s, v, transition=transition)


@cli.command()
@click.argument("state", type=bool, required=False)
@pass_dev
async def led(dev, state):
    """Get or set (Plug's) led state."""
    if state is not None:
        echo(f"Turning led to {state}")
        return await dev.set_led(state)
    else:
        echo(f"LED state: {dev.led}")
        return dev.led


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
async def on(dev: SmartDevice, index: int, name: str, transition: int):
    """Turn the device on."""
    if index is not None or name is not None:
        if not dev.is_strip:
            echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
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
async def off(dev: SmartDevice, index: int, name: str, transition: int):
    """Turn the device off."""
    if index is not None or name is not None:
        if not dev.is_strip:
            echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
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
async def toggle(dev: SmartDevice, index: int, name: str, transition: int):
    """Toggle the device on/off."""
    if index is not None or name is not None:
        if not dev.is_strip:
            echo("Index and name are only for power strips!")
            return

        dev = cast(SmartStrip, dev)
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
def presets_list(dev: SmartBulb):
    """List presets."""
    if not dev.is_bulb:
        echo("Presets only supported on bulbs")
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
async def presets_modify(
    dev: SmartBulb, index, brightness, hue, saturation, temperature
):
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
async def turn_on_behavior(dev: SmartBulb, type, last, preset):
    """Modify bulb turn-on behavior."""
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


if __name__ == "__main__":
    cli()
