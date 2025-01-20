from __future__ import annotations

import logging

import pytest
from pytest_mock import MockerFixture

from kasa import Feature, Module, SmartDevice

from ...device_fixtures import parametrize

childsetup = parametrize(
    "supports pairing", component_filter="childQuickSetup", protocol_filter={"SMARTCAM"}
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
            mocker.call(
                "startScanChildDevice",
                params={
                    "childControl": {
                        "category": [
                            "camera",
                            "subg.trv",
                            "subg.trigger",
                            "subg.plugswitch",
                        ]
                    }
                },
            ),
            mocker.call(
                "getScanChildDeviceList",
                {
                    "childControl": {
                        "category": [
                            "camera",
                            "subg.trv",
                            "subg.trigger",
                            "subg.plugswitch",
                        ]
                    }
                },
            ),
            mocker.call(
                "addScanChildDeviceList",
                {
                    "childControl": {
                        "child_device_list": [
                            {
                                "device_id": "0000000000000000000000000000000000000000",
                                "category": "subg.trigger.button",
                                "device_model": "S200B",
                                "name": "I01BU0tFRF9OQU1FIw====",
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
    dev: SmartDevice, mocker: MockerFixture, caplog: pytest.LogCaptureFixture
):
    """Test unpair."""
    mock_query_helper = mocker.spy(dev, "_query_helper")
    DUMMY_ID = "dummy_id"

    cs = dev.modules.get(Module.ChildSetup)
    assert cs

    await cs.unpair(DUMMY_ID)

    mock_query_helper.assert_awaited_with(
        "removeChildDeviceList",
        params={"childControl": {"child_device_list": [{"device_id": DUMMY_ID}]}},
    )
