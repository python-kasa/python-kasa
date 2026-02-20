"""Module for cli lock control commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import asyncclick as click

from kasa import Device, Module

from .common import echo, error, pass_dev_or_child

if TYPE_CHECKING:
    from kasa.smartcam.modules import Lock, LockHistory


@click.group()
@pass_dev_or_child
def lock(dev: Device) -> None:
    """Commands to control lock settings."""


@lock.command()
@pass_dev_or_child
async def state(dev: Device) -> None:
    """Get lock state."""
    mod = dev.modules.get(Module.SmartCamLock)
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module = cast("Lock", mod)
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")
    echo(f"Battery level: {lock_module.battery_level}%")
    if lock_module.auto_lock_enabled:
        echo(f"Auto-lock enabled: {lock_module.auto_lock_time}s")
    else:
        echo("Auto-lock enabled: false")

    if last_user := lock_module.last_unlock_user:
        echo(f"Last unlocked by: {last_user} ({lock_module.last_unlock_method.value})")


@lock.command()
@pass_dev_or_child
async def unlock(dev: Device) -> None:
    """Unlock the device."""
    mod = dev.modules.get(Module.SmartCamLock)
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module = cast("Lock", mod)
    echo("Unlocking...")
    await lock_module.unlock()
    await dev.update()
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")


@lock.command(name="lock")
@pass_dev_or_child
async def lock_device(dev: Device) -> None:
    """Lock the device."""
    mod = dev.modules.get(Module.SmartCamLock)
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module = cast("Lock", mod)
    echo("Locking...")
    await lock_module.lock()
    await dev.update()
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")


@lock.command()
@pass_dev_or_child
async def history(dev: Device) -> None:
    """Get lock history."""
    mod = dev.modules.get(Module.SmartCamLockHistory)
    if not mod:
        error("This device does not support lock history.")
        return

    history_module = cast("LockHistory", mod)
    echo(f"Total lock events: {history_module.total_log_count}\n")

    if not history_module.logs:
        echo("No lock events recorded.")
        return

    echo("Recent lock events:")
    for i, entry in enumerate(history_module.logs[:10], 1):
        user_info = f" by {entry.user}" if entry.user else ""
        echo(
            f"  {i}. {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{entry.event_type.value.title()}{user_info} ({entry.method.value})"
        )

    if history_module.last_lock:
        timestamp = history_module.last_lock.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        echo(f"\nLast locked: {timestamp}")

    if history_module.last_unlock:
        timestamp = history_module.last_unlock.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        echo(f"Last unlocked: {timestamp}")
