from kasa.smart import SmartDevice

from .conftest import (
    brightness,
)


@brightness
async def test_brightness_component(dev: SmartDevice):
    """Placeholder to test framwework component filter."""
    assert isinstance(dev, SmartDevice)
    assert "brightness" in dev._components
