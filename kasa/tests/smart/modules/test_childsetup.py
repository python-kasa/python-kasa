from __future__ import annotations

import logging

import pytest
from pytest_mock import MockerFixture

from kasa import Feature, Module
from kasa.smart import SmartDevice
from kasa.tests.device_fixtures import parametrize

childsetup = parametrize(
    "supports pairing", component_filter="child_quick_setup", protocol_filter={"SMART"}
)


@childsetup
async def test_childsetup_features(dev: SmartDevice):
    """Test the exposed features."""
    cs = dev.modules.get(Module.ChildSetup)
    assert cs

    assert "pair" in cs._module_features
    pair = cs._module_features["pair"]
    assert pair.type == Feature.Type.Action


@childsetup
async def test_childsetup_pair(
    dev: SmartDevice, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test device pairing."""
    caplog.set_level(logging.INFO)
    mock_query_helper = mocker.spy(dev, "_query_helper")
    mocker.patch("asyncio.sleep")

    cs = dev.modules.get(Module.ChildSetup)
    assert cs

    await cs.pair()

    mock_query_helper.assert_has_awaits(
        [
            mocker.call("begin_scanning_child_device", None),
            mocker.call("get_scan_child_device_list", params=mocker.ANY),
            mocker.call("add_child_device_list", params=mocker.ANY),
        ]
    )
    assert "Discovery done" in caplog.text


@childsetup
async def test_childsetup_unpair(
    dev: SmartDevice, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test unpair."""
    mock_query_helper = mocker.spy(dev, "_query_helper")
    DUMMY_ID = "dummy_id"

    cs = dev.modules.get(Module.ChildSetup)
    assert cs

    await cs.unpair(DUMMY_ID)

    mock_query_helper.assert_awaited_with(
        "remove_child_device_list",
        params={"child_device_list": [{"device_id": DUMMY_ID}]},
    )
