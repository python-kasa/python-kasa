"""Tests that set_brightness/set_color_temp/set_hsv inject device_on correctly.

Regression coverage for two interacting concerns:

* Tapo L900-5 "zombie state" — device reports on but LEDs stay off unless
  device_on is re-asserted in the set_device_info payload.
* Issue #1532 — users want to change brightness on an already-off device
  without turning it on as a side-effect.

The compromise: re-assert device_on=True only when the device is currently on,
otherwise leave it out so an off device stays off.
"""

from __future__ import annotations

import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import get_parent_and_child_modules, parametrize

brightness_smart = parametrize(
    "has brightness", component_filter="brightness", protocol_filter={"SMART"}
)
color_smart = parametrize(
    "has color", component_filter="color", protocol_filter={"SMART"}
)
color_temp_smart = parametrize(
    "has color temperature",
    component_filter="color_temperature",
    protocol_filter={"SMART"},
)


@brightness_smart
@pytest.mark.parametrize("is_on", [True, False])
async def test_set_brightness_device_on_payload(
    dev: SmartDevice, is_on: bool, mocker: MockerFixture
) -> None:
    brightness = next(get_parent_and_child_modules(dev, Module.Brightness))
    owner = brightness._device
    # Bypass any active light effect so set_brightness hits set_device_info.
    if (effect := owner.modules.get(Module.SmartLightEffect)) is not None:
        mocker.patch.object(
            type(effect),
            "is_active",
            new_callable=mocker.PropertyMock,
            return_value=False,
        )

    owner._info["device_on"] = is_on
    mock_call = mocker.patch.object(brightness, "call")

    await brightness.set_brightness(50)

    expected: dict = {"brightness": 50}
    if is_on:
        expected["device_on"] = True
    mock_call.assert_called_once_with("set_device_info", expected)


@color_temp_smart
@pytest.mark.parametrize("is_on", [True, False])
async def test_set_color_temp_device_on_payload(
    dev: SmartDevice, is_on: bool, mocker: MockerFixture
) -> None:
    ct = next(get_parent_and_child_modules(dev, Module.ColorTemperature), None)
    if ct is None:
        pytest.skip("Device has color_temperature component but no module enabled")
    if ct.valid_temperature_range.min == ct.valid_temperature_range.max:
        pytest.skip("Device exposes color_temperature but no usable range")

    ct._device._info["device_on"] = is_on
    mock_call = mocker.patch.object(ct, "call")

    temp = ct.valid_temperature_range.min
    await ct.set_color_temp(temp)

    expected: dict = {"color_temp": temp}
    if is_on:
        expected["device_on"] = True
    mock_call.assert_called_once_with("set_device_info", expected)


@color_smart
@pytest.mark.parametrize("is_on", [True, False])
async def test_set_hsv_device_on_payload(
    dev: SmartDevice, is_on: bool, mocker: MockerFixture
) -> None:
    color = next(get_parent_and_child_modules(dev, Module.Color))

    color._device._info["device_on"] = is_on
    mock_call = mocker.patch.object(color, "call")

    await color.set_hsv(120, 50)

    expected: dict = {"color_temp": 0, "hue": 120, "saturation": 50}
    if is_on:
        expected["device_on"] = True
    mock_call.assert_called_once_with("set_device_info", expected)
