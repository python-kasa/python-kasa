"""Module for cli lock control commands."""

from typing import TYPE_CHECKING

import asyncclick as click

from kasa import Device

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
    mod = dev.modules.get("Lock")
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module: Lock = mod  # type: ignore[assignment]
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")  # type: ignore[attr-defined]
    echo(f"Battery level: {lock_module.battery_level}%")  # type: ignore[attr-defined]
    if lock_module.auto_lock_enabled:  # type: ignore[attr-defined]
        echo(f"Auto-lock enabled: {lock_module.auto_lock_time}s")  # type: ignore[attr-defined]
    else:
        echo("Auto-lock enabled: false")

    if last_user := lock_module.last_unlock_user:  # type: ignore[attr-defined]
        echo(f"Last unlocked by: {last_user} ({lock_module.last_unlock_method.value})")  # type: ignore[attr-defined]


@lock.command()
@pass_dev_or_child
async def unlock(dev: Device) -> None:
    """Unlock the device."""
    mod = dev.modules.get("Lock")
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module: Lock = mod  # type: ignore[assignment]
    echo("Unlocking...")
    await lock_module.unlock()  # type: ignore[attr-defined]
    await dev.update()
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")  # type: ignore[attr-defined]


@lock.command(name="lock")
@pass_dev_or_child
async def lock_device(dev: Device) -> None:
    """Lock the device."""
    mod = dev.modules.get("Lock")
    if not mod:
        error("This device does not support lock control.")
        return

    lock_module: Lock = mod  # type: ignore[assignment]
    echo("Locking...")
    await lock_module.lock()  # type: ignore[attr-defined]
    await dev.update()
    echo(f"Lock state: {'locked' if lock_module.is_locked else 'unlocked'}")  # type: ignore[attr-defined]


@lock.command()
@pass_dev_or_child
async def history(dev: Device) -> None:
    """Get lock history."""
    mod = dev.modules.get("LockHistory")
    if not mod:
        error("This device does not support lock history.")
        return

    history_module: LockHistory = mod  # type: ignore[assignment]
    echo(f"Total lock events: {history_module.total_log_count}\n")  # type: ignore[attr-defined]

    if not history_module.logs:  # type: ignore[attr-defined]
        echo("No lock events recorded.")
        return

    echo("Recent lock events:")
    for i, entry in enumerate(history_module.logs[:10], 1):  # type: ignore[attr-defined]
        user_info = f" by {entry.user}" if entry.user else ""
        echo(
            f"  {i}. {entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
            f"{entry.event_type.value.title()}{user_info} ({entry.method.value})"
        )

    if history_module.last_lock:  # type: ignore[attr-defined]
        timestamp = history_module.last_lock.timestamp.strftime("%Y-%m-%d %H:%M:%S")  # type: ignore[attr-defined]
        echo(f"\nLast locked: {timestamp}")

    if history_module.last_unlock:  # type: ignore[attr-defined]
        timestamp = history_module.last_unlock.timestamp.strftime("%Y-%m-%d %H:%M:%S")  # type: ignore[attr-defined]
        echo(f"Last unlocked: {timestamp}")

    return history_module.logs  # type: ignore
