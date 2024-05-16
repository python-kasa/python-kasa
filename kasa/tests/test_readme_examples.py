import asyncio

import pytest
import xdoctest

from kasa import Discover
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


def test_tutorial_examples(mocker, top_level_await):
    """Test discovery examples."""
    a = asyncio.run(
        get_device_for_fixture_protocol("L530E(EU)_3.0_1.1.6.json", "SMART")
    )
    b = asyncio.run(get_device_for_fixture_protocol("HS110(EU)_1.0_1.2.5.json", "IOT"))
    a.host = "127.0.0.1"
    b.host = "127.0.0.2"

    # Note autospec does not work for staticmethods in python < 3.12
    # https://github.com/python/cpython/issues/102978
    mocker.patch(
        "kasa.discover.Discover.discover_single", return_value=a, autospec=True
    )
    mocker.patch.object(Discover, "discover", return_value=[a, b], autospec=True)
    res = xdoctest.doctest_module("docs/tutorial.py", "all")
    assert not res["failed"]


@pytest.fixture
def top_level_await(mocker):
    """Fixture to enable top level awaits in doctests.

    Uses the async exec feature of python to patch the builtins xdoctest uses.
    See https://github.com/python/cpython/issues/78797
    """
    import ast
    from inspect import CO_COROUTINE

    orig_exec = exec
    orig_eval = eval
    orig_compile = compile

    def patch_exec(source, globals=None, locals=None, /, **kwargs):
        if source.co_flags & CO_COROUTINE == CO_COROUTINE:
            asyncio.run(orig_eval(source, globals, locals))
        else:
            orig_exec(source, globals, locals, **kwargs)

    def patch_eval(source, globals=None, locals=None, /, **kwargs):
        if source.co_flags & CO_COROUTINE == CO_COROUTINE:
            return asyncio.run(orig_eval(source, globals, locals, **kwargs))
        else:
            return orig_eval(source, globals, locals, **kwargs)

    def patch_compile(
        source, filename, mode, flags=0, dont_inherit=False, optimize=-1, **kwargs
    ):
        flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        return orig_compile(
            source, filename, mode, flags, dont_inherit, optimize, **kwargs
        )

    mocker.patch("builtins.eval", side_effect=patch_eval)
    mocker.patch("builtins.exec", side_effect=patch_exec)
    mocker.patch("builtins.compile", side_effect=patch_compile)
