from __future__ import annotations

import copy
from json import loads as json_loads

from kasa import Credentials, DeviceConfig
from kasa.experimental.smartcameraprotocol import SmartCameraProtocol
from kasa.protocol import BaseTransport


class FakeSmartCameraProtocol(SmartCameraProtocol):
    def __init__(self, info, fixture_name):
        super().__init__(
            transport=FakeSmartCameraTransport(info, fixture_name),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so can still patch SmartProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeSmartCameraTransport(BaseTransport):
    def __init__(
        self,
        info,
        fixture_name,
        *,
        list_return_size=10,
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
        self.info = copy.deepcopy(info)
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
                response = self._send_request(request)  # type: ignore[arg-type]
                # Devices do not continue after error
                if response["error_code"] != 0:
                    break
                response["method"] = request["method"]  # type: ignore[index]
                responses.append(response)
            return {"result": {"responses": responses}, "error_code": 0}
        else:
            return self._send_request(request_dict)

    def _handle_control_child(self, params: dict):
        """Handle control_child command."""
        device_id = params.get("device_id")
        request_data = params.get("requestData", {})

        child_method = request_data.get("method")
        child_params = request_data.get("params")  # noqa: F841

        info = self.info
        children = info["get_child_device_list"]["child_device_list"]

        for child in children:
            if child["device_id"] == device_id:
                info = child
                break
        # Create the child_devices fixture section for fixtures generated before it was added
        if "child_devices" not in self.info:
            self.info["child_devices"] = {}
        # Get the method calls made directly on the child devices
        child_device_calls = self.info["child_devices"].setdefault(device_id, {})  # noqa: F841

        # We only support get & set device info for now.
        if child_method == "get_device_info":
            result = copy.deepcopy(info)
            return {"result": result, "error_code": 0}

    @staticmethod
    def _get_param_set_value(info: dict, set_keys: list[str], value):
        for key in set_keys[:-1]:
            info = info[key]
        info[set_keys[-1]] = value

    SETTERS = {
        ("system", "sys", "dev_alias"): [
            "getDeviceInfo",
            "device_info",
            "basic_info",
            "device_alias",
        ]
    }

    def _send_request(self, request_dict: dict):
        method = request_dict["method"]

        info = self.info
        if method == "control_child":
            return self._handle_control_child(request_dict["params"])

        if method == "set":
            for key, val in request_dict.items():
                if key != "method":
                    module = key
                    section = next(iter(val))
                    skey_val = val[section]
                    for skey, sval in skey_val.items():
                        section_key = skey
                        section_value = sval
                    break
            if setter_keys := self.SETTERS.get((module, section, section_key)):
                self._get_param_set_value(info, setter_keys, section_value)
                return {"error_code": 0}
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
