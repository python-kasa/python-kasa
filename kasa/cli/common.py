"""Common cli module."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from contextlib import contextmanager
from functools import singledispatch, update_wrapper, wraps
from gettext import gettext
from typing import TYPE_CHECKING, Any, Final, NoReturn

import asyncclick as click

from kasa import (
    Device,
)

# Value for optional options if passed without a value
OPTIONAL_VALUE_FLAG: Final = "_FLAG_"

# Block list of commands which require no update
SKIP_UPDATE_COMMANDS = ["raw-command", "command"]

pass_dev = click.make_pass_decorator(Device)  # type: ignore[type-abstract]


try:
    from rich import print as _echo
except ImportError:
    # Strip out rich formatting if rich is not installed
    # but only lower case tags to avoid stripping out
    # raw data from the device that is printed from
    # the device state.
    rich_formatting = re.compile(r"\[/?[a-z]+]")

    def _strip_rich_formatting(echo_func):
        """Strip rich formatting from messages."""

        @wraps(echo_func)
        def wrapper(message=None, *args, **kwargs) -> None:
            if message is not None:
                message = rich_formatting.sub("", message)
            echo_func(message, *args, **kwargs)

        return wrapper

    _echo = _strip_rich_formatting(click.echo)


def echo(*args, **kwargs) -> None:
    """Print a message."""
    ctx = click.get_current_context().find_root()
    if "json" not in ctx.params or ctx.params["json"] is False:
        _echo(*args, **kwargs)


def error(msg: str) -> NoReturn:
    """Print an error and exit."""
    echo(f"[bold red]{msg}[/bold red]")
    sys.exit(1)


def json_formatter_cb(result: Any, **kwargs) -> None:
    """Format and output the result as JSON, if requested."""
    if not kwargs.get("json"):
        return

    # Calling the discover command directly always returns a DeviceDict so if host
    # was specified just format the device json
    if (
        (host := kwargs.get("host"))
        and isinstance(result, dict)
        and (dev := result.get(host))
        and isinstance(dev, Device)
    ):
        result = dev

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


async def invoke_subcommand(
    command: click.BaseCommand,
    ctx: click.Context,
    args: list[str] | None = None,
    **extra: Any,
) -> Any:
    """Invoke a click subcommand.

    Calling ctx.Invoke() treats the command like a simple callback and doesn't
    process any result_callbacks so we use this pattern from the click docs
    https://click.palletsprojects.com/en/stable/exceptions/#what-if-i-don-t-want-that.
    """
    if args is None:
        args = []
    sub_ctx = await command.make_context(command.name, args, parent=ctx, **extra)
    async with sub_ctx:
        return await command.invoke(sub_ctx)


def pass_dev_or_child(wrapped_function: Callable) -> Callable:
    """Pass the device or child to the click command based on the child options."""
    child_help = (
        "Child ID or alias for controlling sub-devices. "
        "If no value provided will show an interactive prompt allowing you to "
        "select a child."
    )
    child_index_help = "Child index controlling sub-devices"

    @contextmanager
    def patched_device_update(parent: Device, child: Device):
        try:
            orig_update = child.update
            # patch child update method. Can be removed once update can be called
            # directly on child devices
            child.update = parent.update  # type: ignore[method-assign]
            yield child
        finally:
            child.update = orig_update  # type: ignore[method-assign]

    @click.pass_obj
    @click.pass_context
    @click.option(
        "--child",
        "--name",
        is_flag=False,
        flag_value=OPTIONAL_VALUE_FLAG,
        default=None,
        required=False,
        type=click.STRING,
        help=child_help,
    )
    @click.option(
        "--child-index",
        "--index",
        required=False,
        default=None,
        type=click.INT,
        help=child_index_help,
    )
    async def wrapper(ctx: click.Context, dev, *args, child, child_index, **kwargs):
        if child := await _get_child_device(dev, child, child_index, ctx.info_name):
            ctx.obj = ctx.with_resource(patched_device_update(dev, child))
            dev = child
        return await ctx.invoke(wrapped_function, dev, *args, **kwargs)

    # Update wrapper function to look like wrapped function
    return update_wrapper(wrapper, wrapped_function)


async def _get_child_device(
    device: Device,
    child_option: str | None,
    child_index_option: int | None,
    info_command: str | None,
) -> Device | None:
    def _list_children():
        return "\n".join(
            [
                f"{idx}: {child.device_id} ({child.alias})"
                for idx, child in enumerate(device.children)
            ]
        )

    if child_option is None and child_index_option is None:
        return None

    if info_command in SKIP_UPDATE_COMMANDS:
        # The device hasn't had update called (e.g. for cmd_command)
        # The way child devices are accessed requires a ChildDevice to
        # wrap the communications. Doing this properly would require creating
        # a common interfaces for both IOT and SMART child devices.
        # As a stop-gap solution, we perform an update instead.
        await device.update()

    if not device.children:
        error(f"Device: {device.host} does not have children")

    if child_option is not None and child_index_option is not None:
        raise click.BadOptionUsage(
            "child", "Use either --child or --child-index, not both."
        )

    if child_option is not None:
        if child_option is OPTIONAL_VALUE_FLAG:
            msg = _list_children()
            child_index_option = click.prompt(
                f"\n{msg}\nEnter the index number of the child device",
                type=click.IntRange(0, len(device.children) - 1),
            )
        elif child := device.get_child_device(child_option):
            echo(f"Targeting child device {child.alias}")
            return child
        else:
            error(
                "No child device found with device_id or name: "
                f"{child_option} children are:\n{_list_children()}"
            )

    if TYPE_CHECKING:
        assert isinstance(child_index_option, int)

    if child_index_option + 1 > len(device.children) or child_index_option < 0:
        error(
            f"Invalid index {child_index_option}, "
            f"device has {len(device.children)} children"
        )

    child_by_index = device.children[child_index_option]
    echo(f"Targeting child device {child_by_index.alias}")
    return child_by_index


def CatchAllExceptions(cls):
    """Capture all exceptions and prints them nicely.

    Idea from https://stackoverflow.com/a/44347763 and
    https://stackoverflow.com/questions/52213375
    """

    def _handle_exception(debug, exc) -> None:
        if isinstance(exc, click.ClickException):
            raise
        # Handle exit request from click.
        if isinstance(exc, click.exceptions.Exit):
            sys.exit(exc.exit_code)
        if isinstance(exc, click.exceptions.Abort):
            sys.exit(0)

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

        def __call__(self, *args, **kwargs):
            """Run the coroutine in the event loop and print any exceptions.

            python click catches KeyboardInterrupt in main, raises Abort()
            and does sys.exit. asyncclick doesn't properly handle a coroutine
            receiving CancelledError on a KeyboardInterrupt, so we catch the
            KeyboardInterrupt here once asyncio.run has re-raised it. This
            avoids large stacktraces when a user presses Ctrl-C.
            """
            try:
                asyncio.run(self.main(*args, **kwargs))
            except KeyboardInterrupt:
                click.echo(gettext("\nAborted!"), file=sys.stderr)
                sys.exit(1)

    return _CommandCls
