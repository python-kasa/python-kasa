from kasa.smartprotocol import _ChildProtocolWrapper

from .conftest import strip_smart


@strip_smart
def test_childdevice_init(dev, dummy_protocol, mocker):
    """Test that child devices get initialized and use protocol wrapper."""
    assert len(dev.children) > 0
    assert dev.is_strip

    first = dev.children[0]
    assert isinstance(first.protocol, _ChildProtocolWrapper)

    assert first._info["category"] == "plug.powerstrip.sub-plug"
    assert "position" in first._info


@strip_smart
async def test_childdevice_update(dev, dummy_protocol, mocker):
    """Test that parent update updates children."""
    assert len(dev.children) > 0
    first = dev.children[0]

    child_update = mocker.patch.object(first, "update")
    await dev.update()
    child_update.assert_called()

    assert dev._last_update != first._last_update
    assert dev._last_update["child_info"]["child_device_list"][0] == first._last_update
