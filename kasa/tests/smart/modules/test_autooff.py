from __future__ import annotations

import sys
from datetime import datetime
from typing import Optional

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice
from kasa.tests.device_fixtures import get_parent_and_child_modules, parametrize

autooff = parametrize(
    "has autooff", component_filter="auto_off", protocol_filter={"SMART"}
)


@autooff
@pytest.mark.parametrize(
    "feature, prop_name, type",
    [
        ("auto_off_enabled", "enabled", bool),
        ("auto_off_minutes", "delay", int),
        ("auto_off_at", "auto_off_at", Optional[datetime]),
    ],
)
@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Subscripted generics cannot be used with class and instance checks",
)
async def test_autooff_features(
    dev: SmartDevice, feature: str, prop_name: str, type: type
):
    """Test that features are registered and work as expected."""
    autooff = next(get_parent_and_child_modules(dev, Module.AutoOff))
    assert autooff is not None

    prop = getattr(autooff, prop_name)
    assert isinstance(prop, type)

    feat = autooff._device.features[feature]
    assert feat.value == prop
    assert isinstance(feat.value, type)


@autooff
async def test_settings(dev: SmartDevice, mocker: MockerFixture):
    """Test autooff settings."""
    autooff = next(get_parent_and_child_modules(dev, Module.AutoOff))
    assert autooff

    enabled = autooff._device.features["auto_off_enabled"]
    assert autooff.enabled == enabled.value

    delay = autooff._device.features["auto_off_minutes"]
    assert autooff.delay == delay.value

    call = mocker.spy(autooff, "call")
    new_state = True

    await autooff.set_enabled(new_state)
    call.assert_called_with(
        "set_auto_off_config", {"enable": new_state, "delay_min": delay.value}
    )
    call.reset_mock()
    await dev.update()

    new_delay = 123

    await autooff.set_delay(new_delay)

    call.assert_called_with(
        "set_auto_off_config", {"enable": new_state, "delay_min": new_delay}
    )

    await dev.update()

    assert autooff.enabled == new_state
    assert autooff.delay == new_delay


@autooff
@pytest.mark.parametrize("is_timer_active", [True, False])
async def test_auto_off_at(
    dev: SmartDevice, mocker: MockerFixture, is_timer_active: bool
):
    """Test auto-off at sensor."""
    autooff = next(get_parent_and_child_modules(dev, Module.AutoOff))
    assert autooff

    autooff_at = autooff._device.features["auto_off_at"]

    mocker.patch.object(
        type(autooff),
        "is_timer_active",
        new_callable=mocker.PropertyMock,
        return_value=is_timer_active,
    )
    if is_timer_active:
        assert isinstance(autooff_at.value, datetime)
    else:
        assert autooff_at.value is None
