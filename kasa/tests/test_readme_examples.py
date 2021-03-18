import sys

import pytest
import xdoctest

from kasa.tests.conftest import get_device_for_file


def test_bulb_examples(mocker):
    """Use KL130 (bulb with all features) to test the doctests."""
    p = get_device_for_file("KL130(US)_1.0.json")
    mocker.patch("kasa.smartbulb.SmartBulb", return_value=p)
    mocker.patch("kasa.smartbulb.SmartBulb.update")
    res = xdoctest.doctest_module("kasa.smartbulb", "all")
    assert not res["failed"]


def test_smartdevice_examples(mocker):
    """Use HS110 for emeter examples."""
    p = get_device_for_file("HS110(EU)_1.0_real.json")
    mocker.patch("kasa.smartdevice.SmartDevice", return_value=p)
    mocker.patch("kasa.smartdevice.SmartDevice.update")
    res = xdoctest.doctest_module("kasa.smartdevice", "all")
    assert not res["failed"]


def test_plug_examples(mocker):
    """Test plug examples."""
    p = get_device_for_file("HS110(EU)_1.0_real.json")
    mocker.patch("kasa.smartplug.SmartPlug", return_value=p)
    mocker.patch("kasa.smartplug.SmartPlug.update")
    res = xdoctest.doctest_module("kasa.smartplug", "all")
    assert not res["failed"]


def test_strip_examples(mocker):
    """Test strip examples."""
    p = get_device_for_file("KP303(UK)_1.0.json")
    mocker.patch("kasa.smartstrip.SmartStrip", return_value=p)
    mocker.patch("kasa.smartstrip.SmartStrip.update")
    res = xdoctest.doctest_module("kasa.smartstrip", "all")
    assert not res["failed"]


def test_dimmer_examples(mocker):
    """Test dimmer examples."""
    p = get_device_for_file("HS220(US)_1.0_real.json")
    mocker.patch("kasa.smartdimmer.SmartDimmer", return_value=p)
    mocker.patch("kasa.smartdimmer.SmartDimmer.update")
    res = xdoctest.doctest_module("kasa.smartdimmer", "all")
    assert not res["failed"]


def test_lightstrip_examples(mocker):
    """Test lightstrip examples."""
    p = get_device_for_file("KL430(US)_1.0.json")
    mocker.patch("kasa.smartlightstrip.SmartLightStrip", return_value=p)
    mocker.patch("kasa.smartlightstrip.SmartLightStrip.update")
    res = xdoctest.doctest_module("kasa.smartlightstrip", "all")
    assert not res["failed"]


@pytest.mark.skipif(
    sys.version_info < (3, 8), reason="3.7 handles asyncio.run differently"
)
def test_discovery_examples(mocker):
    """Test discovery examples."""
    p = get_device_for_file("KP303(UK)_1.0.json")

    # This succeeds on python 3.8 but fails on 3.7
    # ValueError: a coroutine was expected, got [<DeviceType.Strip model KP303(UK) ...
    mocker.patch("kasa.discover.Discover.discover", return_value=[p])
    res = xdoctest.doctest_module("kasa.discover", "all")
    assert not res["failed"]
