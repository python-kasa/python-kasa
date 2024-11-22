from pytest_mock import MockerFixture

from kasa import Module
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

    for range in Range:
        await motion.set_range(range)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": range.value},
        )


@dimmer_iot
async def test_motion_threshold(dev: IotDimmer, mocker: MockerFixture):
    motion: Motion = dev.modules[Module.IotMotion]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    for range in Range:
        # Switch to a given range.
        await motion.set_range(range)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": range.value},
        )

        # Assert that the range always goes to custom, regardless of current range.
        await motion.set_threshold(123)
        query_helper.assert_called_with(
            "smartlife.iot.PIR",
            "set_trigger_sens",
            {"index": Range.Custom.value, "value": 123},
        )


@dimmer_iot
def test_motion_feature(dev: IotDimmer):
    assert Module.IotMotion in dev.modules
    motion: Motion = dev.modules[Module.IotMotion]

    pir_enabled = dev.features["pir_enabled"]
    assert motion.enabled == pir_enabled.value
