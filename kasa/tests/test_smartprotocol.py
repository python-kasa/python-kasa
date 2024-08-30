import logging
from typing import cast

import pytest
import pytest_mock

from kasa.smart import SmartDevice

from ..exceptions import (
    SMART_RETRYABLE_ERRORS,
    DeviceError,
    KasaException,
    SmartErrorCode,
)
from ..smartprotocol import SmartProtocol, _ChildProtocolWrapper
from .conftest import device_smart
from .fakeprotocol_smart import FakeSmartTransport

DUMMY_QUERY = {"foobar": {"foo": "bar", "bar": "foo"}}
DUMMY_MULTIPLE_QUERY = {
    "foobar": {"foo": "bar", "bar": "foo"},
    "barfoo": {"foo": "bar", "bar": "foo"},
}
ERRORS = [e for e in SmartErrorCode if e != 0]


async def test_smart_queries(dummy_protocol, mocker: pytest_mock.MockerFixture):
    mock_response = {"result": {"great": "success"}, "error_code": 0}

    mocker.patch.object(dummy_protocol._transport, "send", return_value=mock_response)
    # test sending a method name as a string
    resp = await dummy_protocol.query("foobar")
    assert "foobar" in resp
    assert resp["foobar"] == mock_response["result"]

    # test sending a method name as a dict
    resp = await dummy_protocol.query(DUMMY_QUERY)
    assert "foobar" in resp
    assert resp["foobar"] == mock_response["result"]


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


@pytest.mark.parametrize("error_code", [-13333, 13333])
async def test_smart_device_unknown_errors(
    dummy_protocol, mocker, error_code, caplog: pytest.LogCaptureFixture
):
    """Test handling of unknown error codes."""
    mock_response = {"result": {"great": "success"}, "error_code": error_code}

    send_mock = mocker.patch.object(
        dummy_protocol._transport, "send", return_value=mock_response
    )

    with pytest.raises(KasaException):  # noqa: PT012
        res = await dummy_protocol.query(DUMMY_QUERY)
        assert res is SmartErrorCode.INTERNAL_UNKNOWN_ERROR

    send_mock.assert_called_once()
    assert f"received unknown error code: {error_code}" in caplog.text


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
    dummy_protocol._multi_request_batch_size = batch_size

    await dummy_protocol.query(requests, retry_count=0)
    expected_count = int(request_size / batch_size) + (request_size % batch_size > 0)
    assert send_mock.call_count == expected_count


async def test_smart_device_multiple_request_json_decode_failure(
    dummy_protocol, mocker
):
    """Test the logic to disable multiple requests on JSON_DECODE_FAIL_ERROR."""
    requests = {}
    mock_responses = []

    mock_json_error = {
        "result": {"responses": []},
        "error_code": SmartErrorCode.JSON_DECODE_FAIL_ERROR.value,
    }
    for i in range(10):
        method = f"get_method_{i}"
        requests[method] = {"foo": "bar", "bar": "foo"}
        mock_responses.append(
            {"method": method, "result": {"great": "success"}, "error_code": 0}
        )

    send_mock = mocker.patch.object(
        dummy_protocol._transport,
        "send",
        side_effect=[mock_json_error, *mock_responses],
    )
    dummy_protocol._multi_request_batch_size = 5
    assert dummy_protocol._multi_request_batch_size == 5
    await dummy_protocol.query(requests, retry_count=1)
    assert dummy_protocol._multi_request_batch_size == 1
    # Call count should be the first error + number of requests
    assert send_mock.call_count == len(requests) + 1


async def test_smart_device_multiple_request_json_decode_failure_twice(
    dummy_protocol, mocker
):
    """Test the logic to disable multiple requests on JSON_DECODE_FAIL_ERROR."""
    requests = {}

    mock_json_error = {
        "result": {"responses": []},
        "error_code": SmartErrorCode.JSON_DECODE_FAIL_ERROR.value,
    }
    for i in range(10):
        method = f"get_method_{i}"
        requests[method] = {"foo": "bar", "bar": "foo"}

    send_mock = mocker.patch.object(
        dummy_protocol._transport,
        "send",
        side_effect=[mock_json_error, KasaException],
    )
    dummy_protocol._multi_request_batch_size = 5
    with pytest.raises(KasaException):
        await dummy_protocol.query(requests, retry_count=1)
    assert dummy_protocol._multi_request_batch_size == 1

    assert send_mock.call_count == 2


async def test_smart_device_multiple_request_non_json_decode_failure(
    dummy_protocol, mocker
):
    """Test the logic to disable multiple requests on JSON_DECODE_FAIL_ERROR.

    Ensure other exception types behave as expected.
    """
    requests = {}

    mock_json_error = {
        "result": {"responses": []},
        "error_code": SmartErrorCode.UNKNOWN_METHOD_ERROR.value,
    }
    for i in range(10):
        method = f"get_method_{i}"
        requests[method] = {"foo": "bar", "bar": "foo"}

    send_mock = mocker.patch.object(
        dummy_protocol._transport,
        "send",
        side_effect=[mock_json_error, KasaException],
    )
    dummy_protocol._multi_request_batch_size = 5
    with pytest.raises(DeviceError):
        await dummy_protocol.query(requests, retry_count=1)
    assert dummy_protocol._multi_request_batch_size == 5

    assert send_mock.call_count == 1


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
    res = await wrapped_protocol.query(DUMMY_QUERY)
    assert res["get_device_info"] == {"foo": "bar"}
    assert res["invalid_command"] == SmartErrorCode(-1001)


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


@device_smart
async def test_smart_queries_redaction(
    dev: SmartDevice, caplog: pytest.LogCaptureFixture
):
    """Test query sensitive info redaction."""
    device_id = "123456789ABCDEF"
    cast(FakeSmartTransport, dev.protocol._transport).info["get_device_info"][
        "device_id"
    ] = device_id

    # Info no message logging
    caplog.set_level(logging.INFO)
    await dev.update()
    assert device_id not in caplog.text

    caplog.set_level(logging.DEBUG)

    # Debug no redaction
    caplog.clear()
    dev.protocol._redact_data = False
    await dev.update()
    assert device_id in caplog.text

    # Debug redaction
    caplog.clear()
    dev.protocol._redact_data = True
    await dev.update()
    assert device_id not in caplog.text
    assert "REDACTED_" + device_id[9::] in caplog.text
