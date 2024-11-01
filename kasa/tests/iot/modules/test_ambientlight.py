from pytest_mock import MockerFixture

from kasa import Module
from kasa.iot import IotDimmer
from kasa.iot.modules.ambientlight import AmbientLight
from kasa.tests.device_fixtures import dimmer_iot


@dimmer_iot
def test_ambientlight_getters(dev: IotDimmer):
    assert Module.IotAmbientLight in dev.modules
    ambientlight: AmbientLight = dev.modules[Module.IotAmbientLight]

    assert ambientlight.enabled == ambientlight.config["enable"]
    assert ambientlight.presets == ambientlight.config["level_array"]

    assert (
        ambientlight.ambientlight_brightness
        == ambientlight.data["get_current_brt"]["value"]
    )


@dimmer_iot
async def test_ambientlight_setters(dev: IotDimmer, mocker: MockerFixture):
    ambientlight: AmbientLight = dev.modules[Module.IotAmbientLight]
    query_helper = mocker.patch("kasa.iot.IotDimmer._query_helper")

    await ambientlight.set_enabled(True)
    query_helper.assert_called_with("smartlife.iot.LAS", "set_enable", {"enable": True})

    await ambientlight.set_brightness_limit(10)
    query_helper.assert_called_with(
        "smartlife.iot.LAS", "set_brt_level", {"index": 0, "value": 10}
    )


@dimmer_iot
def test_ambientlight_feature(dev: IotDimmer):
    assert Module.IotAmbientLight in dev.modules
    ambientlight: AmbientLight = dev.modules[Module.IotAmbientLight]

    enabled = dev.features["ambient_light_enabled"]
    assert ambientlight.enabled == enabled.value

    brightness = dev.features["ambient_light"]
    assert ambientlight.ambientlight_brightness == brightness.value
