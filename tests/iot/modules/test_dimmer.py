from datetime import timedelta
from typing import Final

import pytest
from pytest_mock import MockerFixture

from kasa import KasaException, Module
from kasa.iot import IotDimmer
from kasa.iot.modules.dimmer import Dimmer

from ...device_fixtures import dimmer_iot

_TD_ONE_MS: Final[timedelta] = timedelta(milliseconds=1)


@dimmer_iot
def test_dimmer_getters(dev: IotDimmer):
    assert Module.IotDimmer in dev.modules
    dimmer: Dimmer = dev.modules[Module.IotDimmer]

    assert dimmer.threshold_min == dimmer.config["minThreshold"]
    assert int(dimmer.fade_off_time / _TD_ONE_MS) == dimmer.config["fadeOffTime"]
    assert int(dimmer.fade_on_time / _TD_ONE_MS) == dimmer.config["fadeOnTime"]
    assert int(dimmer.gentle_off_time / _TD_ONE_MS) == dimmer.config["gentleOffTime"]
    assert int(dimmer.gentle_on_time / _TD_ONE_MS) == dimmer.config["gentleOnTime"]
    assert dimmer.ramp_rate == dimmer.config["rampRate"]


@dimmer_iot
async def test_dimmer_setters(dev: IotDimmer, mocker: MockerFixture):
    dimmer: Dimmer = dev.modules[Module.IotDimmer]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    test_threshold = 10
    await dimmer.set_threshold_min(test_threshold)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "calibrate_brightness", {"minThreshold": test_threshold}
    )

    test_time = 100
    await dimmer.set_fade_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_off_time", {"fadeTime": test_time}
    )
    await dimmer.set_fade_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_on_time", {"fadeTime": test_time}
    )

    test_time = 1000
    await dimmer.set_gentle_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_off_time", {"duration": test_time}
    )
    await dimmer.set_gentle_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_on_time", {"duration": test_time}
    )

    test_rate = 30
    await dimmer.set_ramp_rate(test_rate)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_button_ramp_rate", {"rampRate": test_rate}
    )


@dimmer_iot
async def test_dimmer_setter_min(dev: IotDimmer, mocker: MockerFixture):
    dimmer: Dimmer = dev.modules[Module.IotDimmer]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    test_threshold = dimmer.THRESHOLD_ABS_MIN
    await dimmer.set_threshold_min(test_threshold)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "calibrate_brightness", {"minThreshold": test_threshold}
    )

    test_time = int(dimmer.FADE_TIME_ABS_MIN / _TD_ONE_MS)
    await dimmer.set_fade_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_off_time", {"fadeTime": test_time}
    )
    await dimmer.set_fade_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_on_time", {"fadeTime": test_time}
    )

    test_time = int(dimmer.GENTLE_TIME_ABS_MIN / _TD_ONE_MS)
    await dimmer.set_gentle_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_off_time", {"duration": test_time}
    )
    await dimmer.set_gentle_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_on_time", {"duration": test_time}
    )

    test_rate = dimmer.RAMP_RATE_ABS_MIN
    await dimmer.set_ramp_rate(test_rate)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_button_ramp_rate", {"rampRate": test_rate}
    )


@dimmer_iot
async def test_dimmer_setter_max(dev: IotDimmer, mocker: MockerFixture):
    dimmer: Dimmer = dev.modules[Module.IotDimmer]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    test_threshold = dimmer.THRESHOLD_ABS_MAX
    await dimmer.set_threshold_min(test_threshold)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "calibrate_brightness", {"minThreshold": test_threshold}
    )

    test_time = int(dimmer.FADE_TIME_ABS_MAX / _TD_ONE_MS)
    await dimmer.set_fade_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_off_time", {"fadeTime": test_time}
    )
    await dimmer.set_fade_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_fade_on_time", {"fadeTime": test_time}
    )

    test_time = int(dimmer.GENTLE_TIME_ABS_MAX / _TD_ONE_MS)
    await dimmer.set_gentle_off_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_off_time", {"duration": test_time}
    )
    await dimmer.set_gentle_on_time(test_time)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_gentle_on_time", {"duration": test_time}
    )

    test_rate = dimmer.RAMP_RATE_ABS_MAX
    await dimmer.set_ramp_rate(test_rate)
    query_helper.assert_called_with(
        "smartlife.iot.dimmer", "set_button_ramp_rate", {"rampRate": test_rate}
    )


@dimmer_iot
async def test_dimmer_setters_min_oob(dev: IotDimmer, mocker: MockerFixture):
    dimmer: Dimmer = dev.modules[Module.IotDimmer]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    test_threshold = dimmer.THRESHOLD_ABS_MIN - 1
    with pytest.raises(KasaException):
        await dimmer.set_threshold_min(test_threshold)
    query_helper.assert_not_called()

    test_time = dimmer.FADE_TIME_ABS_MIN - _TD_ONE_MS
    with pytest.raises(KasaException):
        await dimmer.set_fade_off_time(test_time)
    query_helper.assert_not_called()
    with pytest.raises(KasaException):
        await dimmer.set_fade_on_time(test_time)
    query_helper.assert_not_called()

    test_time = dimmer.GENTLE_TIME_ABS_MIN - _TD_ONE_MS
    with pytest.raises(KasaException):
        await dimmer.set_gentle_off_time(test_time)
    query_helper.assert_not_called()
    with pytest.raises(KasaException):
        await dimmer.set_gentle_on_time(test_time)
    query_helper.assert_not_called()

    test_rate = dimmer.RAMP_RATE_ABS_MIN - 1
    with pytest.raises(KasaException):
        await dimmer.set_ramp_rate(test_rate)
    query_helper.assert_not_called()


@dimmer_iot
async def test_dimmer_setters_max_oob(dev: IotDimmer, mocker: MockerFixture):
    dimmer: Dimmer = dev.modules[Module.IotDimmer]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    test_threshold = dimmer.THRESHOLD_ABS_MAX + 1
    with pytest.raises(KasaException):
        await dimmer.set_threshold_min(test_threshold)
    query_helper.assert_not_called()

    test_time = dimmer.FADE_TIME_ABS_MAX + _TD_ONE_MS
    with pytest.raises(KasaException):
        await dimmer.set_fade_off_time(test_time)
    query_helper.assert_not_called()
    with pytest.raises(KasaException):
        await dimmer.set_fade_on_time(test_time)
    query_helper.assert_not_called()

    test_time = dimmer.GENTLE_TIME_ABS_MAX + _TD_ONE_MS
    with pytest.raises(KasaException):
        await dimmer.set_gentle_off_time(test_time)
    query_helper.assert_not_called()
    with pytest.raises(KasaException):
        await dimmer.set_gentle_on_time(test_time)
    query_helper.assert_not_called()

    test_rate = dimmer.RAMP_RATE_ABS_MAX + 1
    with pytest.raises(KasaException):
        await dimmer.set_ramp_rate(test_rate)
    query_helper.assert_not_called()
