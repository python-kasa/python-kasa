import xdoctest
from kasa.tests.conftest import get_device_for_file


def test_bulb_examples(mocker):
    """Use KL130 (bulb with all features) to test the doctests."""
    p = get_device_for_file("kasa/tests/fixtures/KL130(US)_1.0.json")
    mocker.patch("kasa.smartbulb.SmartBulb", return_value=p)
    mocker.patch("kasa.smartdevice.SmartDevice.update")
    res = xdoctest.doctest_module("kasa.smartbulb", "all")
    assert not res["failed"]


def test_smartdevice_examples(mocker):
    """Use HS110 for emeter examples."""
    p = get_device_for_file("kasa/tests/fixtures/HS110(EU)_1.0_real.json")
    mocker.patch("kasa.smartdevice.SmartDevice", return_value=p)
    mocker.patch("kasa.smartdevice.SmartDevice.update")
    res = xdoctest.doctest_module("kasa.smartdevice", "all")
    assert not res["failed"]
