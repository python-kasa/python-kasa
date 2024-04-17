import asyncio

import xdoctest

from kasa.tests.conftest import get_device_for_fixture_protocol


def test_bulb_examples(mocker):
    """Use KL130 (bulb with all features) to test the doctests."""
    p = asyncio.run(get_device_for_fixture_protocol("KL130(US)_1.0_1.8.11.json", "IOT"))
    mocker.patch("kasa.iot.iotbulb.IotBulb", return_value=p)
    mocker.patch("kasa.iot.iotbulb.IotBulb.update")
    res = xdoctest.doctest_module("kasa.iot.iotbulb", "all")
    assert not res["failed"]


def test_smartdevice_examples(mocker):
    """Use HS110 for emeter examples."""
    p = asyncio.run(get_device_for_fixture_protocol("HS110(EU)_1.0_1.2.5.json", "IOT"))
    mocker.patch("kasa.iot.iotdevice.IotDevice", return_value=p)
    mocker.patch("kasa.iot.iotdevice.IotDevice.update")
    res = xdoctest.doctest_module("kasa.iot.iotdevice", "all")
    assert not res["failed"]


def test_plug_examples(mocker):
    """Test plug examples."""
    p = asyncio.run(get_device_for_fixture_protocol("HS110(EU)_1.0_1.2.5.json", "IOT"))
    # p = await get_device_for_fixture_protocol("HS110(EU)_1.0_1.2.5.json", "IOT")
    mocker.patch("kasa.iot.iotplug.IotPlug", return_value=p)
    mocker.patch("kasa.iot.iotplug.IotPlug.update")
    res = xdoctest.doctest_module("kasa.iot.iotplug", "all")
    assert not res["failed"]


def test_strip_examples(mocker):
    """Test strip examples."""
    p = asyncio.run(get_device_for_fixture_protocol("KP303(UK)_1.0_1.0.3.json", "IOT"))
    mocker.patch("kasa.iot.iotstrip.IotStrip", return_value=p)
    mocker.patch("kasa.iot.iotstrip.IotStrip.update")
    res = xdoctest.doctest_module("kasa.iot.iotstrip", "all")
    assert not res["failed"]


def test_dimmer_examples(mocker):
    """Test dimmer examples."""
    p = asyncio.run(get_device_for_fixture_protocol("HS220(US)_1.0_1.5.7.json", "IOT"))
    mocker.patch("kasa.iot.iotdimmer.IotDimmer", return_value=p)
    mocker.patch("kasa.iot.iotdimmer.IotDimmer.update")
    res = xdoctest.doctest_module("kasa.iot.iotdimmer", "all")
    assert not res["failed"]


def test_lightstrip_examples(mocker):
    """Test lightstrip examples."""
    p = asyncio.run(get_device_for_fixture_protocol("KL430(US)_1.0_1.0.10.json", "IOT"))
    mocker.patch("kasa.iot.iotlightstrip.IotLightStrip", return_value=p)
    mocker.patch("kasa.iot.iotlightstrip.IotLightStrip.update")
    res = xdoctest.doctest_module("kasa.iot.iotlightstrip", "all")
    assert not res["failed"]


def test_discovery_examples(mocker):
    """Test discovery examples."""
    p = asyncio.run(get_device_for_fixture_protocol("KP303(UK)_1.0_1.0.3.json", "IOT"))

    mocker.patch("kasa.discover.Discover.discover", return_value=[p])
    res = xdoctest.doctest_module("kasa.discover", "all")
    assert not res["failed"]
