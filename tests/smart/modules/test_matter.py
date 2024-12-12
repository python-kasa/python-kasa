from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

matter = parametrize("has matter", component_filter="matter", protocol_filter={"SMART"})


@matter
async def test_info(dev: SmartDevice):
    """Test matter info."""
    matter = dev.modules.get(Module.Matter)
    assert matter
    assert matter.info
