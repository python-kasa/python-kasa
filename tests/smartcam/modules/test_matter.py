from kasa import Module
from kasa.smart import SmartDevice

from ...device_fixtures import parametrize

matter = parametrize(
    "has matter", component_filter="matter", protocol_filter={"SMARTCAM"}
)


@matter
async def test_info(dev: SmartDevice):
    """Test matter info."""
    matter = dev.modules.get(Module.Matter)
    assert matter
    assert matter.info
    setup_code = dev.features.get("matter_setup_code")
    assert setup_code
    setup_payload = dev.features.get("matter_setup_payload")
    assert setup_payload
