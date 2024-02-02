import asyncio

import xdoctest

from kasa.tests.conftest import get_device_for_file


def test_bulb_examples(mocker):
    """Use KL130 (bulb with all features) to test the doctests."""
    p = asyncio.run(get_device_for_file("KL130(US)_1.0_1.8.11.json", "IOT"))
    mocker.patch("kasa.iot.bulb.IotBulb", return_value=p)
    mocker.patch("kasa.iot.bulb.IotBulb.update")
    res = xdoctest.doctest_module("kasa.iot.bulb", "all")
    assert not res["failed"]


def test_smartdevice_examples(mocker):
    """Use HS110 for emeter examples."""
    p = asyncio.run(get_device_for_file("HS110(EU)_1.0_1.2.5.json", "IOT"))
    mocker.patch("kasa.iot.device.IotDevice", return_value=p)
    mocker.patch("kasa.iot.device.IotDevice.update")
    res = xdoctest.doctest_module("kasa.iot.device", "all")
    assert not res["failed"]


def test_plug_examples(mocker):
    """Test plug examples."""
    p = asyncio.run(get_device_for_file("HS110(EU)_1.0_1.2.5.json", "IOT"))
    mocker.patch("kasa.iot.plug.IotPlug", return_value=p)
    mocker.patch("kasa.iot.plug.IotPlug.update")
    res = xdoctest.doctest_module("kasa.iot.plug", "all")
    assert not res["failed"]


def test_strip_examples(mocker):
    """Test strip examples."""
    p = asyncio.run(get_device_for_file("KP303(UK)_1.0_1.0.3.json", "IOT"))
    mocker.patch("kasa.iot.strip.IotStrip", return_value=p)
    mocker.patch("kasa.iot.strip.IotStrip.update")
    res = xdoctest.doctest_module("kasa.iot.strip", "all")
    assert not res["failed"]


def test_dimmer_examples(mocker):
    """Test dimmer examples."""
    p = asyncio.run(get_device_for_file("HS220(US)_1.0_1.5.7.json", "IOT"))
    mocker.patch("kasa.iot.dimmer.IotDimmer", return_value=p)
    mocker.patch("kasa.iot.dimmer.IotDimmer.update")
    res = xdoctest.doctest_module("kasa.iot.dimmer", "all")
    assert not res["failed"]


def test_lightstrip_examples(mocker):
    """Test lightstrip examples."""
    p = asyncio.run(get_device_for_file("KL430(US)_1.0_1.0.10.json", "IOT"))
    mocker.patch("kasa.iot.lightstrip.IotLightStrip", return_value=p)
    mocker.patch("kasa.iot.lightstrip.IotLightStrip.update")
    res = xdoctest.doctest_module("kasa.iot.lightstrip", "all")
    assert not res["failed"]


def test_discovery_examples(mocker):
    """Test discovery examples."""
    p = asyncio.run(get_device_for_file("KP303(UK)_1.0_1.0.3.json", "IOT"))

    mocker.patch("kasa.discover.Discover.discover", return_value=[p])
    res = xdoctest.doctest_module("kasa.discover", "all")
    assert not res["failed"]
