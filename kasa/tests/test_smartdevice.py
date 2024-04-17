"""Tests for SMART devices."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pytest_mock import MockerFixture

from kasa import KasaException
from kasa.exceptions import SmartErrorCode
from kasa.smart import SmartBulb, SmartDevice

from .conftest import (
    bulb_smart,
    device_smart,
)


@device_smart
async def test_try_get_response(dev: SmartDevice, caplog):
    mock_response: dict = {
        "get_device_info": SmartErrorCode.PARAMS_ERROR,
    }
    caplog.set_level(logging.DEBUG)
    dev._try_get_response(mock_response, "get_device_info", {})
    msg = "Error PARAMS_ERROR(-1008) getting request get_device_info for device 127.0.0.123"
    assert msg in caplog.text


@device_smart
async def test_update_no_device_info(dev: SmartDevice, mocker: MockerFixture):
    mock_response: dict = {
        "get_device_usage": {},
        "get_device_time": {},
    }
    msg = f"get_device_info not found in {mock_response} for device 127.0.0.123"
    with mocker.patch.object(
        dev.protocol, "query", return_value=mock_response
    ), pytest.raises(KasaException, match=msg):
        await dev.update()


@device_smart
async def test_initial_update(dev: SmartDevice, mocker: MockerFixture):
    """Test the initial update cycle."""
    # As the fixture data is already initialized, we reset the state for testing
    dev._components_raw = None
    dev._features = {}

    negotiate = mocker.spy(dev, "_negotiate")
    initialize_modules = mocker.spy(dev, "_initialize_modules")
    initialize_features = mocker.spy(dev, "_initialize_features")

    # Perform two updates and verify that initialization is only done once
    await dev.update()
    await dev.update()

    negotiate.assert_called_once()
    assert dev._components_raw is not None
    initialize_modules.assert_called_once()
    assert dev.modules
    initialize_features.assert_called_once()
    assert dev.features


@device_smart
async def test_negotiate(dev: SmartDevice, mocker: MockerFixture):
    """Test that the initial negotiation performs expected steps."""
    # As the fixture data is already initialized, we reset the state for testing
    dev._components_raw = None
    dev._children = {}

    query = mocker.spy(dev.protocol, "query")
    initialize_children = mocker.spy(dev, "_initialize_children")
    await dev._negotiate()

    # Check that we got the initial negotiation call
    query.assert_any_call({"component_nego": None, "get_device_info": None})
    assert dev._components_raw

    # Check the children are created, if device supports them
    if "child_device" in dev._components:
        initialize_children.assert_called_once()
        query.assert_any_call(
            {
                "get_child_device_component_list": None,
                "get_child_device_list": None,
            }
        )
        assert len(dev.children) == dev.internal_state["get_child_device_list"]["sum"]


@device_smart
async def test_update_module_queries(dev: SmartDevice, mocker: MockerFixture):
    """Test that the regular update uses queries from all supported modules."""
    query = mocker.spy(dev.protocol, "query")

    # We need to have some modules initialized by now
    assert dev.modules

    await dev.update()
    full_query: dict[str, Any] = {}
    for mod in dev.modules.values():
        full_query = {**full_query, **mod.query()}

    query.assert_called_with(full_query)


@bulb_smart
async def test_smartdevice_brightness(dev: SmartBulb):
    """Test brightness setter and getter."""
    assert isinstance(dev, SmartDevice)
    assert "brightness" in dev._components

    # Test getting the value
    feature = dev.features["brightness"]
    assert feature.minimum_value == 1
    assert feature.maximum_value == 100

    await dev.set_brightness(10)
    await dev.update()
    assert dev.brightness == 10

    with pytest.raises(ValueError):
        await dev.set_brightness(feature.minimum_value - 10)

    with pytest.raises(ValueError):
        await dev.set_brightness(feature.maximum_value + 10)
