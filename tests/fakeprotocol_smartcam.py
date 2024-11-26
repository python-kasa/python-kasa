from __future__ import annotations

import copy
from json import loads as json_loads
from typing import Any

from kasa import Credentials, DeviceConfig, SmartProtocol
from kasa.protocols.smartcamprotocol import SmartCamProtocol
from kasa.transports.basetransport import BaseTransport

from .fakeprotocol_smart import FakeSmartTransport


class FakeSmartCamProtocol(SmartCamProtocol):
    def __init__(self, info, fixture_name, *, is_child=False, verbatim=False):
        super().__init__(
            transport=FakeSmartCamTransport(
                info, fixture_name, is_child=is_child, verbatim=verbatim
            ),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so can still patch SmartProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeSmartCamTransport(BaseTransport):
    def __init__(
        self,
        info,
        fixture_name,
        *,
        list_return_size=10,
        is_child=False,
        verbatim=False,
    ):
        super().__init__(
            config=DeviceConfig(
                "127.0.0.123",
                credentials=Credentials(
                    username="dummy_user",
                    password="dummy_password",  # noqa: S106
                ),
            ),
        )
        self.fixture_name = fixture_name
        # When True verbatim will bypass any extra processing of missing
        # methods and is used to test the fixture creation itself.
        self.verbatim = verbatim
        if not is_child:
            self.info = copy.deepcopy(info)
            self.child_protocols = FakeSmartTransport._get_child_protocols(
                self.info, self.fixture_name, "getChildDeviceList"
            )
        else:
            self.info = info
        # self.child_protocols = self._get_child_protocols()
        self.list_return_size = list_return_size

    @property
    def default_port(self):
        """Default port for the transport."""
        return 443

    @property
    def credentials_hash(self):
        """The hashed credentials used by the transport."""
        return self._credentials.username + self._credentials.password + "camerahash"

    async def send(self, request: str):
        request_dict = json_loads(request)
        method = request_dict["method"]

        if method == "multipleRequest":
            params = request_dict["params"]
            responses = []
            for request in params["requests"]:
                response = await self._send_request(request)  # type: ignore[arg-type]
                response["method"] = request["method"]  # type: ignore[index]
                responses.append(response)
                # Devices do not continue after error
                if response["error_code"] != 0:
                    break
            return {"result": {"responses": responses}, "error_code": 0}
        else:
            return await self._send_request(request_dict)

    async def _handle_control_child(self, params: dict):
        """Handle control_child command."""
        device_id = params.get("device_id")
        assert device_id in self.child_protocols, "Fixture does not have child info"

        child_protocol: SmartProtocol = self.child_protocols[device_id]

        request_data = params.get("request_data", {})

        child_method = request_data.get("method")
        child_params = request_data.get("params")  # noqa: F841

        resp = await child_protocol.query({child_method: child_params})
        resp["error_code"] = 0
        for val in resp.values():
            return {
                "result": {"response_data": {"result": val, "error_code": 0}},
                "error_code": 0,
            }

    @staticmethod
    def _get_param_set_value(info: dict, set_keys: list[str], value):
        for key in set_keys[:-1]:
            info = info[key]
        info[set_keys[-1]] = value

    # Setters for when there's not a simple mapping of setters to getters
    SETTERS = {
        ("system", "sys", "dev_alias"): [
            "getDeviceInfo",
            "device_info",
            "basic_info",
            "device_alias",
        ],
        # setTimezone maps to getClockStatus
        ("system", "clock_status", "seconds_from_1970"): [
            "getClockStatus",
            "system",
            "clock_status",
            "seconds_from_1970",
        ],
        # setTimezone maps to getClockStatus
        ("system", "clock_status", "local_time"): [
            "getClockStatus",
            "system",
            "clock_status",
            "local_time",
        ],
    }

    @staticmethod
    def _get_second_key(request_dict: dict[str, Any]) -> str:
        assert (
            len(request_dict) == 2
        ), f"Unexpected dict {request_dict}, should be length 2"
        it = iter(request_dict)
        next(it, None)
        return next(it)

    async def _send_request(self, request_dict: dict):
        method = request_dict["method"]

        info = self.info
        if method == "controlChild":
            return await self._handle_control_child(
                request_dict["params"]["childControl"]
            )

        if method[:3] == "set":
            get_method = "g" + method[1:]
            for key, val in request_dict.items():
                if key == "method":
                    continue
                # key is params for multi request and the actual params
                # for single requests
                if key == "params":
                    module = next(iter(val))
                    val = val[module]
                else:
                    module = key
                section = next(iter(val))
                skey_val = val[section]
                if not isinstance(skey_val, dict):  # single level query
                    section_key = section
                    section_val = skey_val
                    if (get_info := info.get(get_method)) and section_key in get_info:
                        get_info[section_key] = section_val
                    else:
                        return {"error_code": -1}
                    break
                for skey, sval in skey_val.items():
                    section_key = skey
                    section_value = sval
                    if setter_keys := self.SETTERS.get((module, section, section_key)):
                        self._get_param_set_value(info, setter_keys, section_value)
                    elif (
                        section := info.get(get_method, {})
                        .get(module, {})
                        .get(section, {})
                    ) and section_key in section:
                        section[section_key] = section_value
                    else:
                        return {"error_code": -1}
                break
            return {"error_code": 0}
        elif method == "get":
            module = self._get_second_key(request_dict)
            get_method = f"get_{module}"
            if get_method in info:
                result = copy.deepcopy(info[get_method]["get"])
                return {**result, "error_code": 0}
            else:
                return {"error_code": -1}
        elif method[:3] == "get":
            params = request_dict.get("params")
            if method in info:
                result = copy.deepcopy(info[method])
                if "start_index" in result and "sum" in result:
                    list_key = next(
                        iter([key for key in result if isinstance(result[key], list)])
                    )
                    start_index = (
                        start_index
                        if (params and (start_index := params.get("start_index")))
                        else 0
                    )

                    result[list_key] = result[list_key][
                        start_index : start_index + self.list_return_size
                    ]
                return {"result": result, "error_code": 0}
            else:
                return {"error_code": -1}
        return {"error_code": -1}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
