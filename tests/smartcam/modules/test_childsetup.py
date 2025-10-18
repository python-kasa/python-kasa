from __future__ import annotations

import logging

import pytest
from pytest_mock import MockerFixture

from kasa import Device, Feature, Module

from ...device_fixtures import parametrize

childsetup = parametrize(
    "supports pairing", component_filter="childQuickSetup", protocol_filter={"SMARTCAM"}
)


@childsetup
async def test_childsetup_features(dev: Device):
    """Test the exposed features."""
    cs = dev.modules[Module.ChildSetup]

    assert "pair" in cs._module_features
    pair = cs._module_features["pair"]
    assert pair.type == Feature.Type.Action


@childsetup
async def test_childsetup_pair(
    dev: Device, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test device pairing."""
    caplog.set_level(logging.INFO)
    mock_query_helper = mocker.spy(dev, "_query_helper")
    mocker.patch("asyncio.sleep")

    cs = dev.modules[Module.ChildSetup]

    await cs.pair()

    mock_query_helper.assert_has_awaits(
        [
            mocker.call(
                "startScanChildDevice",
                params={"childControl": {"category": cs.supported_categories}},
            ),
            mocker.call(
                "getScanChildDeviceList",
                {"childControl": {"category": cs.supported_categories}},
            ),
            mocker.call(
                "addScanChildDeviceList",
                {
                    "childControl": {
                        "child_device_list": [
                            {
                                "device_id": mocker.ANY,
                                "category": mocker.ANY,
                                "device_model": mocker.ANY,
                                "name": mocker.ANY,
                            }
                        ]
                    }
                },
            ),
        ]
    )
    assert "Discovery done" in caplog.text


@childsetup
async def test_childsetup_unpair(
    dev: Device, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test unpair."""
    mock_query_helper = mocker.spy(dev, "_query_helper")
    DUMMY_ID = "dummy_id"

    cs = dev.modules[Module.ChildSetup]

    await cs.unpair(DUMMY_ID)

    mock_query_helper.assert_awaited_with(
        "removeChildDeviceList",
        params={"childControl": {"child_device_list": [{"device_id": DUMMY_ID}]}},
    )
