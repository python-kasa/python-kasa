import click
import logging
from click_datetime import Datetime
from pprint import pformat

from pyHS100 import SmartPlug, TPLinkSmartHomeProtocol

pass_dev = click.make_pass_decorator(SmartPlug)


@click.group(invoke_without_command=True)
@click.option('--ip', envvar="PYHS100_IP", required=False)
@click.option('--debug/--normal', default=False)
@click.pass_context
def cli(ctx, ip, debug):
    """A cli tool for controlling TP-Link smart home plugs."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if ctx.invoked_subcommand == "discover":
        return

    plug = SmartPlug(ip)
    ctx.obj = plug

    if ctx.invoked_subcommand is None:
        ctx.invoke(state)


@cli.command()
@click.option('--timeout', default=5, required=False)
def discover(timeout):
    """Discover devices in the network."""
    click.echo("Discovering devices for %s seconds" % timeout)
    for dev in TPLinkSmartHomeProtocol.discover(timeout=timeout):
        print("Found device: %s" % pformat(dev))


@cli.command()
@pass_dev
def sysinfo(plug):
    """Print out full system information."""
    click.echo(click.style("== System info ==", bold=True))
    click.echo(pformat(plug.sys_info))


@cli.command()
@pass_dev
@click.pass_context
def state(ctx, plug):
    """Print out device state and versions."""
    click.echo(click.style("== %s - %s ==" % (plug.alias, plug.model),
                           bold=True))

    click.echo(click.style("Device state: %s" % plug.state,
                           fg="green" if plug.is_on else "red"))
    click.echo("LED state:    %s" % plug.led)
    click.echo("Time:         %s" % plug.time)
    click.echo("On since:     %s" % plug.on_since)
    click.echo("Hardware:     %s" % plug.hw_info["hw_ver"])
    click.echo("Software:     %s" % plug.hw_info["sw_ver"])
    click.echo("MAC (rssi):   %s (%s)" % (plug.mac, plug.rssi))
    click.echo("Location:     %s" % plug.location)
    ctx.invoke(emeter)


@cli.command()
@pass_dev
@click.option('--year', type=Datetime(format='%Y'),
              default=None, required=False)
@click.option('--month', type=Datetime(format='%Y-%m'),
              default=None, required=False)
@click.option('--erase', is_flag=True)
def emeter(plug, year, month, erase):
    """Query emeter for historical consumption."""
    click.echo(click.style("== Emeter ==", bold=True))
    if not plug.has_emeter:
        click.echo("Device has no emeter")
        return

    if erase:
        click.echo("Erasing emeter statistics..")
        plug.erase_emeter_stats()
        return

    click.echo("Current state: %s" % plug.get_emeter_realtime())
    if year:
        click.echo("== For year %s ==" % year.year)
        click.echo(plug.get_emeter_monthly(year.year))
    elif month:
        click.echo("== For month %s of %s ==" % (month.month, month.year))
        plug.get_emeter_daily(year=month.year, month=month.month)


@cli.command()
@click.argument('state', type=bool, required=False)
@pass_dev
def led(plug, state):
    """Get or set led state."""
    if state is not None:
        click.echo("Turning led to %s" % state)
        plug.led = state
    else:
        click.echo("LED state: %s" % plug.led)


@cli.command()
@pass_dev
def on(plug):
    """Turn the device on."""
    click.echo("Turning on..")
    plug.turn_on()


@cli.command()
@pass_dev
def off(plug):
    """Turn the device off."""
    click.echo("Turning off..")
    plug.turn_off()


if __name__ == "__main__":
    cli()
