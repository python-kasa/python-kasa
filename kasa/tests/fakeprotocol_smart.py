import copy
from json import loads as json_loads

import pytest

from kasa import Credentials, DeviceConfig, SmartProtocol
from kasa.exceptions import SmartErrorCode
from kasa.protocol import BaseTransport


class FakeSmartProtocol(SmartProtocol):
    def __init__(self, info, fixture_name):
        super().__init__(
            transport=FakeSmartTransport(info, fixture_name),
        )

    async def query(self, request, retry_count: int = 3):
        """Implement query here so can still patch SmartProtocol.query."""
        resp_dict = await self._query(request, retry_count)
        return resp_dict


class FakeSmartTransport(BaseTransport):
    def __init__(
        self,
        info,
        fixture_name,
        *,
        list_return_size=10,
        component_nego_not_included=False,
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
        if not component_nego_not_included:
            self.components = {
                comp["id"]: comp["ver_code"]
                for comp in self.info["component_nego"]["component_list"]
            }
        self.list_return_size = list_return_size

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
        "get_auto_off_config": ("auto_off", {"delay_min": 10, "enable": False}),
        "get_led_info": (
            "led",
            {
                "led_rule": "never",
                "led_status": False,
                "night_mode": {
                    "end_time": 420,
                    "night_mode_type": "sunrise_sunset",
                    "start_time": 1140,
                    "sunrise_offset": 0,
                    "sunset_offset": 0,
                },
            },
        ),
        "get_on_off_gradually_info": ("on_off_gradually", {"enable": True}),
        "get_latest_fw": (
            "firmware",
            {
                "fw_size": 0,
                "fw_ver": "1.0.5 Build 230801 Rel.095702",
                "hw_id": "",
                "need_to_upgrade": False,
                "oem_id": "",
                "release_date": "",
                "release_note": "",
                "type": 0,
            },
        ),
        "get_auto_update_info": (
            "firmware",
            {"enable": True, "random_range": 120, "time": 180},
        ),
        "get_alarm_configure": (
            "alarm",
            {
                "get_alarm_configure": {
                    "duration": 10,
                    "type": "Doorbell Ring 2",
                    "volume": "low",
                }
            },
        ),
        "get_support_alarm_type_list": (
            "alarm",
            {
                "alarm_type_list": [
                    "Doorbell Ring 1",
                ]
            },
        ),
        "get_device_usage": ("device", {}),
    }

    async def send(self, request: str):
        request_dict = json_loads(request)
        method = request_dict["method"]
        params = request_dict["params"]
        if method == "multipleRequest":
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
        child_params = request_data.get("params")

        info = self.info
        children = info["get_child_device_list"]["child_device_list"]

        for child in children:
            if child["device_id"] == device_id:
                info = child
                break

        # We only support get & set device info for now.
        if child_method == "get_device_info":
            result = copy.deepcopy(info)
            return {"result": result, "error_code": 0}
        elif child_method == "set_device_info":
            info.update(child_params)
            return {"error_code": 0}
        elif (
            # FIXTURE_MISSING is for service calls not in place when
            # SMART fixtures started to be generated
            missing_result := self.FIXTURE_MISSING_MAP.get(child_method)
        ) and missing_result[0] in self.components:
            result = copy.deepcopy(missing_result[1])
            retval = {"result": result, "error_code": 0}
            return retval
        else:
            # PARAMS error returned for KS240 when get_device_usage called
            # on parent device.  Could be any error code though.
            # TODO: Try to figure out if there's a way to prevent the KS240 smartdevice
            # calling the unsupported device in the first place.
            retval = {
                "error_code": SmartErrorCode.PARAMS_ERROR.value,
                "method": child_method,
            }
            return retval

        raise NotImplementedError(
            "Method %s not implemented for children" % child_method
        )

    def _set_light_effect(self, info, params):
        """Set or remove values as per the device behaviour."""
        info["get_device_info"]["dynamic_light_effect_enable"] = params["enable"]
        info["get_dynamic_light_effect_rules"]["enable"] = params["enable"]
        if params["enable"]:
            info["get_device_info"]["dynamic_light_effect_id"] = params["id"]
            info["get_dynamic_light_effect_rules"]["current_rule_id"] = params["enable"]
        else:
            if "dynamic_light_effect_id" in info["get_device_info"]:
                del info["get_device_info"]["dynamic_light_effect_id"]
            if "current_rule_id" in info["get_dynamic_light_effect_rules"]:
                del info["get_dynamic_light_effect_rules"]["current_rule_id"]

    def _send_request(self, request_dict: dict):
        method = request_dict["method"]
        params = request_dict["params"]

        info = self.info
        if method == "control_child":
            return self._handle_control_child(params)
        elif method == "component_nego" or method[:4] == "get_":
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

            if (
                # FIXTURE_MISSING is for service calls not in place when
                # SMART fixtures started to be generated
                missing_result := self.FIXTURE_MISSING_MAP.get(method)
            ) and missing_result[0] in self.components:
                result = copy.deepcopy(missing_result[1])
                retval = {"result": result, "error_code": 0}
            else:
                # PARAMS error returned for KS240 when get_device_usage called
                # on parent device.  Could be any error code though.
                # TODO: Try to figure out if there's a way to prevent the KS240 smartdevice
                # calling the unsupported device in the first place.
                retval = {
                    "error_code": SmartErrorCode.PARAMS_ERROR.value,
                    "method": method,
                }
            # Reduce warning spam by consolidating and reporting at the end of the run
            if self.fixture_name not in pytest.fixtures_missing_methods:
                pytest.fixtures_missing_methods[self.fixture_name] = set()
            pytest.fixtures_missing_methods[self.fixture_name].add(method)
            return retval
        elif method in ["set_qs_info", "fw_download"]:
            return {"error_code": 0}
        elif method == "set_dynamic_light_effect_rule_enable":
            self._set_light_effect(info, params)
            return {"error_code": 0}
        elif method[:4] == "set_":
            target_method = f"get_{method[4:]}"
            info[target_method].update(params)
            return {"error_code": 0}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
