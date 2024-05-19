import logging

import pytest

from ..credentials import Credentials
from ..deviceconfig import DeviceConfig
from ..exceptions import (
    SMART_RETRYABLE_ERRORS,
    KasaException,
    SmartErrorCode,
)
from ..smartprotocol import SmartProtocol, _ChildProtocolWrapper
from .fakeprotocol_smart import FakeSmartTransport

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}
DUMMY_MULTIPLE_QUERY = {
    "foobar": {"foo": "bar", "bar": "foo"},
    "barfoo": {"foo": "bar", "bar": "foo"},
}
ERRORS = [e for e in SmartErrorCode if e != 0]


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors(dummy_protocol, mocker, error_code):
    mock_response = {"result": {"great": "success"}, "error_code": error_code.value}

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )

    with pytest.raises(KasaException):
        await dummy_protocol.query(DUMMY_QUERY, retry_count=2)

    expected_calls = 3 if error_code in SMART_RETRYABLE_ERRORS else 1
    assert send_mock.call_count == expected_calls


@pytest.mark.parametrize("error_code", ERRORS, ids=lambda e: e.name)
async def test_smart_device_errors_in_multiple_request(
    dummy_protocol, mocker, error_code
):
    mock_request = {
        "foobar1": {"foo": "bar", "bar": "foo"},
        "foobar2": {"foo": "bar", "bar": "foo"},
        "foobar3": {"foo": "bar", "bar": "foo"},
    }
    mock_response = {
        "result": {
            "responses": [
                {"method": "foobar1", "result": {"great": "success"}, "error_code": 0},
                {
                    "method": "foobar2",
                    "result": {"great": "success"},
                    "error_code": error_code.value,
                },
                {"method": "foobar3", "result": {"great": "success"}, "error_code": 0},
            ]
        },
        "error_code": 0,
    }

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )

    resp_dict = await dummy_protocol.query(mock_request, retry_count=2)
    assert resp_dict["foobar2"] == error_code
    assert send_mock.call_count == 1
    assert len(resp_dict) == len(mock_request)


@pytest.mark.parametrize("request_size", [1, 3, 5, 10])
@pytest.mark.parametrize("batch_size", [1, 2, 3, 4, 5])
async def test_smart_device_multiple_request(
    dummy_protocol, mocker, request_size, batch_size
):
    host = "127.0.0.1"
    requests = {}
    mock_response = {
        "result": {"responses": []},
        "error_code": 0,
    }
    for i in range(request_size):
        method = f"get_method_{i}"
        requests[method] = {"foo": "bar", "bar": "foo"}
        mock_response["result"]["responses"].append(
            {"method": method, "result": {"great": "success"}, "error_code": 0}
        )

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )
    config = DeviceConfig(
        host, credentials=Credentials("foo", "bar"), batch_size=batch_size
    )
    dummy_protocol._transport._config = config

    await dummy_protocol.query(requests, retry_count=0)
    expected_count = int(request_size / batch_size) + (request_size % batch_size > 0)
    assert send_mock.call_count == expected_count


async def test_childdevicewrapper_unwrapping(dummy_protocol, mocker):
    """Test that responseData gets unwrapped correctly."""
    wrapped_protocol = _ChildProtocolWrapper("dummyid", dummy_protocol)
    mock_response = {"error_code": 0, "result": {"responseData": {"error_code": 0}}}

    mocker.patch.object(wrapped_protocol._transport, "send", return_value=mock_response)
    res = await wrapped_protocol.query(DUMMY_QUERY)
    assert res == {"foobar": None}


async def test_childdevicewrapper_unwrapping_with_payload(dummy_protocol, mocker):
    wrapped_protocol = _ChildProtocolWrapper("dummyid", dummy_protocol)
    mock_response = {
        "error_code": 0,
        "result": {"responseData": {"error_code": 0, "result": {"bar": "bar"}}},
    }
    mocker.patch.object(wrapped_protocol._transport, "send", return_value=mock_response)
    res = await wrapped_protocol.query(DUMMY_QUERY)
    assert res == {"foobar": {"bar": "bar"}}


async def test_childdevicewrapper_error(dummy_protocol, mocker):
    """Test that errors inside the responseData payload cause an exception."""
    wrapped_protocol = _ChildProtocolWrapper("dummyid", dummy_protocol)
    mock_response = {"error_code": 0, "result": {"responseData": {"error_code": -1001}}}

    mocker.patch.object(wrapped_protocol._transport, "send", return_value=mock_response)
    with pytest.raises(KasaException):
        await wrapped_protocol.query(DUMMY_QUERY)


async def test_childdevicewrapper_unwrapping_multiplerequest(dummy_protocol, mocker):
    """Test that unwrapping multiplerequest works correctly."""
    mock_response = {
        "error_code": 0,
        "result": {
            "responseData": {
                "result": {
                    "responses": [
                        {
                            "error_code": 0,
                            "method": "get_device_info",
                            "result": {"foo": "bar"},
                        },
                        {
                            "error_code": 0,
                            "method": "second_command",
                            "result": {"bar": "foo"},
                        },
                    ]
                }
            }
        },
    }
    wrapped_protocol = _ChildProtocolWrapper("dummyid", dummy_protocol)
    mocker.patch.object(wrapped_protocol._transport, "send", return_value=mock_response)
    resp = await wrapped_protocol.query(DUMMY_QUERY)
    assert resp == {"get_device_info": {"foo": "bar"}, "second_command": {"bar": "foo"}}


async def test_childdevicewrapper_multiplerequest_error(dummy_protocol, mocker):
    """Test that errors inside multipleRequest response of responseData raise an exception."""
    mock_response = {
        "error_code": 0,
        "result": {
            "responseData": {
                "result": {
                    "responses": [
                        {
                            "error_code": 0,
                            "method": "get_device_info",
                            "result": {"foo": "bar"},
                        },
                        {"error_code": -1001, "method": "invalid_command"},
                    ]
                }
            }
        },
    }
    wrapped_protocol = _ChildProtocolWrapper("dummyid", dummy_protocol)
    mocker.patch.object(wrapped_protocol._transport, "send", return_value=mock_response)
    with pytest.raises(KasaException):
        await wrapped_protocol.query(DUMMY_QUERY)


@pytest.mark.parametrize("list_sum", [5, 10, 30])
@pytest.mark.parametrize("batch_size", [1, 2, 3, 50])
async def test_smart_protocol_lists_single_request(mocker, list_sum, batch_size):
    child_device_list = [{"foo": i} for i in range(list_sum)]
    response = {
        "get_child_device_list": {
            "child_device_list": child_device_list,
            "start_index": 0,
            "sum": list_sum,
        }
    }
    request = {"get_child_device_list": None}

    ft = FakeSmartTransport(
        response,
        "foobar",
        list_return_size=batch_size,
        component_nego_not_included=True,
    )
    protocol = SmartProtocol(transport=ft)
    query_spy = mocker.spy(protocol, "_execute_query")
    resp = await protocol.query(request)
    expected_count = int(list_sum / batch_size) + (1 if list_sum % batch_size else 0)
    assert query_spy.call_count == expected_count
    assert resp == response


@pytest.mark.parametrize("list_sum", [5, 10, 30])
@pytest.mark.parametrize("batch_size", [1, 2, 3, 50])
async def test_smart_protocol_lists_multiple_request(mocker, list_sum, batch_size):
    child_list = [{"foo": i} for i in range(list_sum)]
    response = {
        "get_child_device_list": {
            "child_device_list": child_list,
            "start_index": 0,
            "sum": list_sum,
        },
        "get_child_device_component_list": {
            "child_component_list": child_list,
            "start_index": 0,
            "sum": list_sum,
        },
    }
    request = {"get_child_device_list": None, "get_child_device_component_list": None}

    ft = FakeSmartTransport(
        response,
        "foobar",
        list_return_size=batch_size,
        component_nego_not_included=True,
    )
    protocol = SmartProtocol(transport=ft)
    query_spy = mocker.spy(protocol, "_execute_query")
    resp = await protocol.query(request)
    expected_count = 1 + 2 * (
        int(list_sum / batch_size) + (0 if list_sum % batch_size else -1)
    )
    assert query_spy.call_count == expected_count
    assert resp == response


async def test_incomplete_list(mocker, caplog):
    """Test for handling incomplete lists returned from queries."""
    info = {
        "get_preset_rules": {
            "start_index": 0,
            "states": [
                {
                    "brightness": 50,
                },
                {
                    "brightness": 100,
                },
            ],
            "sum": 7,
        }
    }
    caplog.set_level(logging.ERROR)
    transport = FakeSmartTransport(
        info,
        "dummy-name",
        component_nego_not_included=True,
        warn_fixture_missing_methods=False,
    )
    protocol = SmartProtocol(transport=transport)
    resp = await protocol.query({"get_preset_rules": None})
    assert resp
    assert resp["get_preset_rules"]["sum"] == 2  # FakeTransport fixes sum
    assert caplog.text == ""

    # Test behaviour without FakeTranport fix
    transport = FakeSmartTransport(
        info,
        "dummy-name",
        component_nego_not_included=True,
        warn_fixture_missing_methods=False,
        fix_incomplete_fixture_lists=False,
    )
    protocol = SmartProtocol(transport=transport)
    resp = await protocol.query({"get_preset_rules": None})
    assert resp["get_preset_rules"]["sum"] == 7
    assert (
        "Device 127.0.0.123 returned empty results list for method get_preset_rules"
        in caplog.text
    )
