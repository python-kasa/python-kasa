import pytest

from kasa.iot.modules.homekit import HomeKit


class DummyDevice:
    def __init__(self, last_update):
        self._last_update = last_update
        self.sys_info = {}
        self._is_hub_child = False
        self._components = {}
        self._parent = None

    @property
    def _last_update(self):
        return self.__last_update

    @_last_update.setter
    def _last_update(self, value):
        self.__last_update = value


@pytest.fixture
def homekit_device():
    response = {
        "smartlife.iot.homekit": {
            "setup_info_get": {
                "setup_code": "REDACTED_SETUP_CODE",
                "setup_payload": "REDACTED_SETUP_PAYLOAD",
                "err_code": 0,
            }
        }
    }
    device = DummyDevice(last_update=response)
    return device


@pytest.mark.asyncio
async def test_homekit_getters(homekit_device):
    module = HomeKit(homekit_device, "homekit")
    # Patch query to do nothing (not used in this test)
    module.query = lambda: {"smartlife.iot.homekit": {"setup_info_get": {}}}
    info = module.info["smartlife.iot.homekit"]["setup_info_get"]
    assert info["setup_code"] == "REDACTED_SETUP_CODE"
    assert info["setup_payload"] == "REDACTED_SETUP_PAYLOAD"
    assert info["err_code"] == 0
    assert (
        module.info["smartlife.iot.homekit"]["setup_info_get"]["setup_code"]
        == module.setup_code
    )
    assert (
        module.info["smartlife.iot.homekit"]["setup_info_get"]["setup_payload"]
        == module.setup_payload
    )


@pytest.mark.asyncio
async def test_homekit_feature(homekit_device):
    module = HomeKit(homekit_device, "homekit")
    module.query = lambda: {"smartlife.iot.homekit": {"setup_info_get": {}}}
    module._initialize_features()
    # Check that the feature is added and returns correct value
    feature = module._all_features.get("homekit_setup_code")
    assert feature is not None
    # Simulate feature getter
    value = feature.attribute_getter(module)
    assert value == "REDACTED_SETUP_CODE"
