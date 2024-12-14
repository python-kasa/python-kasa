from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

homekit = parametrize(
    "has homekit", component_filter="homekit", protocol_filter={"SMART"}
)


@homekit
async def test_info(dev: SmartDevice):
    """Test homekit info."""
    homekit = dev.modules.get(Module.HomeKit)
    assert homekit
    assert homekit.info
