"""Tests for smartcam lock module."""

from __future__ import annotations

from datetime import datetime

from kasa import Device
from kasa.interfaces.lock import LockEvent, LockMethod

from ...device_fixtures import parametrize

lock_smartcam = parametrize(
    "has lock",
    component_filter="lock",
    protocol_filter={"SMARTCAM", "SMARTCAM.CHILD"},
)


@lock_smartcam
async def test_lock_module_exists(dev: Device) -> None:
    """Test that lock module is initialized."""
    lock = dev.modules.get("Lock")
    assert lock
    assert hasattr(lock, "is_locked")  # type: ignore[attr-defined]
    assert hasattr(lock, "battery_level")  # type: ignore[attr-defined]
    assert hasattr(lock, "auto_lock_enabled")  # type: ignore[attr-defined]


@lock_smartcam
async def test_lock_properties(dev: Device) -> None:
    """Test lock properties are accessible."""
    lock = dev.modules.get("Lock")
    assert lock

    # Test properties exist and can be accessed
    is_locked = lock.is_locked  # type: ignore[attr-defined]
    assert isinstance(is_locked, bool)

    battery = lock.battery_level  # type: ignore[attr-defined]
    assert battery is None or isinstance(battery, int)

    auto_lock = lock.auto_lock_enabled  # type: ignore[attr-defined]
    assert isinstance(auto_lock, bool)

    auto_lock_time = lock.auto_lock_time  # type: ignore[attr-defined]
    assert auto_lock_time is None or isinstance(auto_lock_time, int)

    last_method = lock.last_unlock_method  # type: ignore[attr-defined]
    assert isinstance(last_method, LockMethod)

    last_user = lock.last_unlock_user  # type: ignore[attr-defined]
    assert last_user is None or isinstance(last_user, str)

    last_time = lock.last_unlock_time  # type: ignore[attr-defined]
    assert last_time is None or isinstance(last_time, datetime)


@lock_smartcam
async def test_lock_features(dev: Device) -> None:
    """Test lock features are created."""
    lock = dev.modules.get("Lock")
    assert lock

    feat_ids = {
        "lock",
        "auto_lock_enabled",
        "auto_lock_time",
    }
    for feat_id in feat_ids:
        feat = dev.features.get(feat_id)
        assert feat, f"Feature {feat_id} not found"
        # Battery level can be None in some cases, also allow auto_lock_time to be None
        if feat_id not in ("auto_lock_time",):
            assert feat.value is not None

    # battery_level is provided by the Battery module, not Lock module
    battery_feat = dev.features.get("battery_level")
    assert battery_feat, "Feature battery_level not found (provided by Battery module)"


@lock_smartcam
async def test_lock_history_module_exists(dev: Device) -> None:
    """Test that lock history module is initialized."""
    history = dev.modules.get("LockHistory")
    assert history
    assert hasattr(history, "logs")  # type: ignore[attr-defined]
    assert hasattr(history, "total_log_count")  # type: ignore[attr-defined]


@lock_smartcam
async def test_lock_history_properties(dev: Device) -> None:
    """Test lock history properties."""
    history = dev.modules.get("LockHistory")
    assert history

    # Test total count
    total = history.total_log_count  # type: ignore[attr-defined]
    assert isinstance(total, int)
    assert total >= 0

    # Test logs
    logs = history.logs  # type: ignore[attr-defined]
    assert isinstance(logs, list)

    # Test log entries have correct structure
    for log in logs:
        assert isinstance(log.timestamp, datetime)
        assert isinstance(log.event_type, LockEvent)  # type: ignore[attr-defined]
        assert isinstance(log.method, LockMethod)
        assert log.user is None or isinstance(log.user, str)

    # Test filtering methods
    recent_locks = history.recent_locks  # type: ignore[attr-defined]
    assert isinstance(recent_locks, list)
    for log in recent_locks:
        assert log.event_type == LockEvent.Lock  # type: ignore[attr-defined]

    recent_unlocks = history.recent_unlocks  # type: ignore[attr-defined]
    assert isinstance(recent_unlocks, list)
    for log in recent_unlocks:
        assert log.event_type == LockEvent.Unlock  # type: ignore[attr-defined]

    # Test last entries
    last_lock = history.last_lock  # type: ignore[attr-defined]
    assert last_lock is None or isinstance(last_lock, object)
    if last_lock:
        assert last_lock.event_type == LockEvent.Lock  # type: ignore[attr-defined]

    last_unlock = history.last_unlock  # type: ignore[attr-defined]
    assert last_unlock is None or isinstance(last_unlock, object)
    if last_unlock:
        assert last_unlock.event_type == LockEvent.Unlock  # type: ignore[attr-defined]
