import warnings
from json import loads as json_loads

from kasa import Credentials, DeviceConfig, SmartDeviceException, SmartProtocol
from kasa.protocol import BaseTransport


class FakeSmartProtocol(SmartProtocol):
    def __init__(self, info):
        super().__init__(
            transport=FakeSmartTransport(info),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so can still patch SmartProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeSmartTransport(BaseTransport):
    def __init__(self, info):
        super().__init__(
            config=DeviceConfig(
                "127.0.0.123",
                credentials=Credentials(
                    username="dummy_user",
                    password="dummy_password",  # noqa: S106
                ),
            ),
        )
        self.info = info
        self.components = {
            comp["id"]: comp["ver_code"]
            for comp in self.info["component_nego"]["component_list"]
        }

    @property
    def default_port(self):
        """Default port for the transport."""
        return 80

    @property
    def credentials_hash(self):
        """The hashed credentials used by the transport."""
        return self._credentials.username + self._credentials.password + "hash"

    FIXTURE_MISSING_MAP = {
        "get_wireless_scan_info": ("wireless", {"ap_list": [], "wep_supported": False}),
    }

    async def send(self, request: str):
        request_dict = json_loads(request)
        method = request_dict["method"]
        params = request_dict["params"]
        if method == "multipleRequest":
            responses = []
            for request in params["requests"]:
                response = self._send_request(request)  # type: ignore[arg-type]
                response["method"] = request["method"]  # type: ignore[index]
                responses.append(response)
            return {"result": {"responses": responses}, "error_code": 0}
        else:
            return self._send_request(request_dict)

    def _send_request(self, request_dict: dict):
        method = request_dict["method"]
        params = request_dict["params"]

        info = self.info
        if method == "control_child":
            device_id = params.get("device_id")
            request_data = params.get("requestData")

            child_method = request_data.get("method")
            child_params = request_data.get("params")

            children = info["get_child_device_list"]["child_device_list"]

            for child in children:
                if child["device_id"] == device_id:
                    info = child
                    break

            # We only support get & set device info for now.
            if child_method == "get_device_info":
                return {"result": info, "error_code": 0}
            elif child_method == "set_device_info":
                info.update(child_params)
                return {"error_code": 0}

            raise NotImplementedError(
                "Method %s not implemented for children" % child_method
            )

        if method == "component_nego" or method[:4] == "get_":
            if method in info:
                return {"result": info[method], "error_code": 0}
            elif (
                missing_result := self.FIXTURE_MISSING_MAP.get(method)
            ) and missing_result[0] in self.components:
                warnings.warn(
                    UserWarning(
                        f"Fixture missing expected method {method}, try to regenerate"
                    ),
                    stacklevel=1,
                )
                return {"result": missing_result[1], "error_code": 0}
            else:
                raise SmartDeviceException(f"Fixture doesn't support {method}")
        elif method == "set_qs_info":
            return {"error_code": 0}
        elif method[:4] == "set_":
            target_method = f"get_{method[4:]}"
            info[target_method].update(params)
            return {"error_code": 0}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
