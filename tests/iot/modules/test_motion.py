import pytest
from pytest_mock import MockerFixture

from kasa import Module
from kasa.exceptions import KasaException
from kasa.iot import IotDimmer
from kasa.iot.modules.motion import Motion, Range

from ...device_fixtures import dimmer_iot


@dimmer_iot
def test_motion_getters(dev: IotDimmer):
    assert Module.IotMotion in dev.modules
    motion: Motion = dev.modules[Module.IotMotion]

    assert motion.enabled == motion.config["enable"]
    assert motion.inactivity_timeout == motion.config["cold_time"]
    assert motion.range.value == motion.config["trigger_index"]


@dimmer_iot
async def test_motion_setters(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    await motion.set_enabled(True)
    query_helper.assert_called_with("smartlife.iot.PIR", "set_enable", {"enable": True})

    await motion.set_inactivity_timeout(10)
    query_helper.assert_called_with(
        "smartlife.iot.PIR", "set_cold_time", {"cold_time": 10}
    )


@dimmer_iot
async def test_motion_range(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    await motion.set_range(value=123)
    query_helper.assert_called_with(
        "smartlife.iot.PIR",
        "set_trigger_sens",
        {"index": Range.Custom.value, "value": 123},
    )

    await motion.set_range(range=Range.Custom, value=123)
    query_helper.assert_called_with(
        "smartlife.iot.PIR",
        "set_trigger_sens",
        {"index": Range.Custom.value, "value": 123},
    )

    await motion.set_range(range=Range.Far)
    query_helper.assert_called_with(
        "smartlife.iot.PIR", "set_trigger_sens", {"index": Range.Far.value}
    )

    with pytest.raises(KasaException, match="Refusing to set non-custom range"):
        await motion.set_range(range=Range.Near, value=100)  # type: ignore[call-overload]

    with pytest.raises(
        KasaException, match="Either range or value needs to be defined"
    ):
        await motion.set_range()  # type: ignore[call-overload]


@dimmer_iot
def test_motion_feature(dev: IotDimmer):
    assert Module.IotMotion in dev.modules
    motion: Motion = dev.modules[Module.IotMotion]

    pir_enabled = dev.features["pir_enabled"]
    assert motion.enabled == pir_enabled.value
