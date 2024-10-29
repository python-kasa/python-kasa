import copy
from json import loads as json_loads
from warnings import warn

import pytest

from kasa import Credentials, DeviceConfig, SmartProtocol
from kasa.exceptions import SmartErrorCode
from kasa.protocol import BaseTransport
from kasa.smart import SmartChildDevice


class FakeSmartProtocol(SmartProtocol):
    def __init__(self, info, fixture_name, *, is_child=False):
        super().__init__(
            transport=FakeSmartTransport(info, fixture_name, is_child=is_child),
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
        warn_fixture_missing_methods=True,
        fix_incomplete_fixture_lists=True,
        is_child=False,
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
        # Don't copy the dict if the device is a child so that updates on the
        # child are then still reflected on the parent's lis of child device in
        if not is_child:
            self.info = copy.deepcopy(info)
            self.child_protocols = self._get_child_protocols(
                self.info, self.fixture_name, "get_child_device_list"
            )
        else:
            self.info = info
        if not component_nego_not_included:
            self.components = {
                comp["id"]: comp["ver_code"]
                for comp in self.info["component_nego"]["component_list"]
            }
        self.list_return_size = list_return_size
        self.warn_fixture_missing_methods = warn_fixture_missing_methods
        self.fix_incomplete_fixture_lists = fix_incomplete_fixture_lists

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
        "get_connect_cloud_state": ("cloud_connect", {"status": 0}),
    }

    async def send(self, request: str):
        request_dict = json_loads(request)
        method = request_dict["method"]

        if method == "multipleRequest":
            params = request_dict["params"]
            responses = []
            for request in params["requests"]:
                response = await self._send_request(request)  # type: ignore[arg-type]
                # Devices do not continue after error
                if response["error_code"] != 0:
                    break
                response["method"] = request["method"]  # type: ignore[index]
                responses.append(response)
            return {"result": {"responses": responses}, "error_code": 0}
        else:
            return await self._send_request(request_dict)

    @staticmethod
    def _get_child_protocols(
        parent_fixture_info, parent_fixture_name, child_devices_key
    ):
        child_infos = parent_fixture_info.get(child_devices_key, {}).get(
            "child_device_list", []
        )
        if not child_infos:
            return
        found_child_fixture_infos = []
        child_protocols = {}
        # imported here to avoid circular import
        from .conftest import filter_fixtures

        def try_get_child_fixture_info(child_dev_info):
            hw_version = child_dev_info["hw_ver"]
            sw_version = child_dev_info["fw_ver"]
            sw_version = sw_version.split(" ")[0]
            model = child_dev_info["model"]
            region = child_dev_info.get("specs", "XX")
            child_fixture_name = f"{model}({region})_{hw_version}_{sw_version}"
            child_fixtures = filter_fixtures(
                "Child fixture",
                protocol_filter={"SMART.CHILD"},
                model_filter={child_fixture_name},
            )
            if child_fixtures:
                return next(iter(child_fixtures))
            return None

        for child_info in child_infos:
            if (  # Is SMART protocol
                (device_id := child_info.get("device_id"))
                and (category := child_info.get("category"))
                and category in SmartChildDevice.CHILD_DEVICE_TYPE_MAP
            ):
                if fixture_info_tuple := try_get_child_fixture_info(child_info):
                    child_fixture = copy.deepcopy(fixture_info_tuple.data)
                    child_fixture["get_device_info"]["device_id"] = device_id
                    found_child_fixture_infos.append(child_fixture["get_device_info"])
                    child_protocols[device_id] = FakeSmartProtocol(
                        child_fixture, fixture_info_tuple.name, is_child=True
                    )
                # Look for fixture inline
                elif (child_fixtures := parent_fixture_info.get("child_devices")) and (
                    child_fixture := child_fixtures.get(device_id)
                ):
                    found_child_fixture_infos.append(child_fixture["get_device_info"])
                    child_protocols[device_id] = FakeSmartProtocol(
                        child_fixture,
                        f"{parent_fixture_name}-{device_id}",
                        is_child=True,
                    )
                else:
                    warn(
                        f"Could not find child SMART fixture for {child_info}",
                        stacklevel=1,
                    )
            else:
                warn(
                    f"Child is a cameraprotocol which needs to be implemented {child_info}",
                    stacklevel=1,
                )
        # Replace parent child infos with the infos from the child fixtures so
        # that updates update both
        if child_infos and found_child_fixture_infos:
            parent_fixture_info[child_devices_key]["child_device_list"] = (
                found_child_fixture_infos
            )
        return child_protocols

    async def _handle_control_child(self, params: dict):
        """Handle control_child command."""
        device_id = params.get("device_id")
        if device_id not in self.child_protocols:
            warn(
                f"Could not find child fixture {device_id} in {self.fixture_name}",
                stacklevel=1,
            )
            return self._handle_control_child_missing(params)

        child_protocol: SmartProtocol = self.child_protocols[device_id]

        request_data = params.get("requestData", {})

        child_method = request_data.get("method")
        child_params = request_data.get("params")  # noqa: F841

        resp = await child_protocol.query({child_method: child_params})
        resp["error_code"] = 0
        for val in resp.values():
            return {
                "result": {"responseData": {"result": val, "error_code": 0}},
                "error_code": 0,
            }

    def _handle_control_child_missing(self, params: dict):
        """Handle control_child command.

        Used for older fixtures where child info wasn't stored in the fixture.
        TODO: Should be removed somehow for future maintanability.
        """
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
        # Create the child_devices fixture section for fixtures generated before it was added
        if "child_devices" not in self.info:
            self.info["child_devices"] = {}
        # Get the method calls made directly on the child devices
        child_device_calls = self.info["child_devices"].setdefault(device_id, {})

        # We only support get & set device info in this method for missing.
        if child_method == "get_device_info":
            result = copy.deepcopy(info)
            return {"result": result, "error_code": 0}
        elif child_method == "set_device_info":
            info.update(child_params)
            return {"error_code": 0}
        elif child_method == "set_preset_rules":
            return self._set_child_preset_rules(info, child_params)
        elif child_method == "set_on_off_gradually_info":
            return self._set_on_off_gradually_info(info, child_params)
        elif child_method in child_device_calls:
            result = copy.deepcopy(child_device_calls[child_method])
            return {"result": result, "error_code": 0}
        elif (
            # FIXTURE_MISSING is for service calls not in place when
            # SMART fixtures started to be generated
            missing_result := self.FIXTURE_MISSING_MAP.get(child_method)
        ) and missing_result[0] in self.components:
            # Copy to info so it will work with update methods
            child_device_calls[child_method] = copy.deepcopy(missing_result[1])
            result = copy.deepcopy(info[child_method])
            retval = {"result": result, "error_code": 0}
            return retval
        elif child_method[:4] == "set_":
            target_method = f"get_{child_method[4:]}"
            if target_method not in child_device_calls:
                raise RuntimeError(
                    f"No {target_method} in child info, calling set before get not supported."
                )
            child_device_calls[target_method].update(child_params)
            return {"error_code": 0}
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

    def _get_on_off_gradually_info(self, info, params):
        if self.components["on_off_gradually"] == 1:
            info["get_on_off_gradually_info"] = {"enable": True}
        else:
            info["get_on_off_gradually_info"] = {
                "off_state": {"duration": 5, "enable": False, "max_duration": 60},
                "on_state": {"duration": 5, "enable": False, "max_duration": 60},
            }
        return copy.deepcopy(info["get_on_off_gradually_info"])

    def _set_on_off_gradually_info(self, info, params):
        # Child devices can have the required properties directly in info

        # the _handle_control_child_missing directly passes in get_device_info
        sys_info = info.get("get_device_info", info)

        if self.components["on_off_gradually"] == 1:
            info["get_on_off_gradually_info"] = {"enable": params["enable"]}
        elif on_state := params.get("on_state"):
            if "fade_on_time" in sys_info and "gradually_on_mode" in sys_info:
                sys_info["gradually_on_mode"] = 1 if on_state["enable"] else 0
                if "duration" in on_state:
                    sys_info["fade_on_time"] = on_state["duration"]
            if "get_on_off_gradually_info" in info:
                info["get_on_off_gradually_info"]["on_state"]["enable"] = on_state[
                    "enable"
                ]
                if "duration" in on_state:
                    info["get_on_off_gradually_info"]["on_state"]["duration"] = (
                        on_state["duration"]
                    )
        elif off_state := params.get("off_state"):
            if "fade_off_time" in sys_info and "gradually_off_mode" in sys_info:
                sys_info["gradually_off_mode"] = 1 if off_state["enable"] else 0
                if "duration" in off_state:
                    sys_info["fade_off_time"] = off_state["duration"]
            if "get_on_off_gradually_info" in info:
                info["get_on_off_gradually_info"]["off_state"]["enable"] = off_state[
                    "enable"
                ]
                if "duration" in off_state:
                    info["get_on_off_gradually_info"]["off_state"]["duration"] = (
                        off_state["duration"]
                    )
        return {"error_code": 0}

    def _set_dynamic_light_effect(self, info, params):
        """Set or remove values as per the device behaviour."""
        info["get_device_info"]["dynamic_light_effect_enable"] = params["enable"]
        info["get_dynamic_light_effect_rules"]["enable"] = params["enable"]
        if params["enable"]:
            info["get_device_info"]["dynamic_light_effect_id"] = params["id"]
            info["get_dynamic_light_effect_rules"]["current_rule_id"] = params["id"]
        else:
            if "dynamic_light_effect_id" in info["get_device_info"]:
                del info["get_device_info"]["dynamic_light_effect_id"]
            if "current_rule_id" in info["get_dynamic_light_effect_rules"]:
                del info["get_dynamic_light_effect_rules"]["current_rule_id"]

    def _set_edit_dynamic_light_effect_rule(self, info, params):
        """Edit dynamic light effect rule."""
        rules = info["get_dynamic_light_effect_rules"]["rule_list"]
        for rule in rules:
            if rule["id"] == params["id"]:
                rule.update(params)
                return

        raise Exception("Unable to find rule with id")

    def _set_light_strip_effect(self, info, params):
        """Set or remove values as per the device behaviour."""
        # Brightness is not always available
        if (brightness := params.get("brightness")) is not None:
            info["get_device_info"]["lighting_effect"]["brightness"] = brightness
        if "enable" in params:
            info["get_device_info"]["lighting_effect"]["enable"] = params["enable"]
            info["get_device_info"]["lighting_effect"]["name"] = params["name"]
            info["get_device_info"]["lighting_effect"]["id"] = params["id"]
            info["get_lighting_effect"] = copy.deepcopy(params)

    def _set_led_info(self, info, params):
        """Set or remove values as per the device behaviour."""
        info["get_led_info"]["led_status"] = params["led_rule"] != "never"
        info["get_led_info"]["led_rule"] = params["led_rule"]

    def _set_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        if "brightness" not in info["get_preset_rules"]:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["get_preset_rules"]["brightness"] = params["brightness"]
        # So far the only child device with light preset (KS240) also has the
        # data available to read in the device_info.
        device_info = info["get_device_info"]
        if "preset_state" in device_info:
            device_info["preset_state"] = [
                {"brightness": b} for b in params["brightness"]
            ]
        return {"error_code": 0}

    def _set_child_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        # So far the only child device with light preset (KS240) has the
        # data available to read in the device_info.  If a child device
        # appears that doesn't have this this will need to be extended.
        if "preset_state" not in info:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["preset_state"] = [{"brightness": b} for b in params["brightness"]]
        return {"error_code": 0}

    def _edit_preset_rules(self, info, params):
        """Set or remove values as per the device behaviour."""
        if "states" not in info["get_preset_rules"] is None:
            return {"error_code": SmartErrorCode.PARAMS_ERROR}
        info["get_preset_rules"]["states"][params["index"]] = params["state"]
        return {"error_code": 0}

    async def _send_request(self, request_dict: dict):
        method = request_dict["method"]

        info = self.info
        if method == "control_child":
            return await self._handle_control_child(request_dict["params"])

        params = request_dict.get("params")
        if method == "component_nego" or method[:4] == "get_":
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
                    # Fixtures generated before _handle_response_lists was implemented
                    # could have incomplete lists.
                    if (
                        len(result[list_key]) < result["sum"]
                        and self.fix_incomplete_fixture_lists
                    ):
                        result["sum"] = len(result[list_key])
                        if self.warn_fixture_missing_methods:
                            pytest.fixtures_missing_methods.setdefault(  # type: ignore[attr-defined]
                                self.fixture_name, set()
                            ).add(f"{method} (incomplete '{list_key}' list)")

                    result[list_key] = result[list_key][
                        start_index : start_index + self.list_return_size
                    ]
                return {"result": result, "error_code": 0}

            if (
                # FIXTURE_MISSING is for service calls not in place when
                # SMART fixtures started to be generated
                missing_result := self.FIXTURE_MISSING_MAP.get(method)
            ) and missing_result[0] in self.components:
                # Copy to info so it will work with update methods
                info[method] = copy.deepcopy(missing_result[1])
                result = copy.deepcopy(info[method])
                retval = {"result": result, "error_code": 0}
            elif (
                method == "get_on_off_gradually_info"
                and "on_off_gradually" in self.components
            ):
                # Need to call a method here to determine which version schema to return
                result = self._get_on_off_gradually_info(info, params)
                return {"result": result, "error_code": 0}
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
            if self.warn_fixture_missing_methods:
                pytest.fixtures_missing_methods.setdefault(  # type: ignore[attr-defined]
                    self.fixture_name, set()
                ).add(method)
            return retval
        elif method in ["set_qs_info", "fw_download"]:
            return {"error_code": 0}
        elif method == "set_dynamic_light_effect_rule_enable":
            self._set_dynamic_light_effect(info, params)
            return {"error_code": 0}
        elif method == "edit_dynamic_light_effect_rule":
            self._set_edit_dynamic_light_effect_rule(info, params)
            return {"error_code": 0}
        elif method == "set_lighting_effect":
            self._set_light_strip_effect(info, params)
            return {"error_code": 0}
        elif method == "set_led_info":
            self._set_led_info(info, params)
            return {"error_code": 0}
        elif method == "set_preset_rules":
            return self._set_preset_rules(info, params)
        elif method == "edit_preset_rules":
            return self._edit_preset_rules(info, params)
        elif method == "set_on_off_gradually_info":
            return self._set_on_off_gradually_info(info, params)
        elif method[:4] == "set_":
            target_method = f"get_{method[4:]}"
            info[target_method].update(params)
            return {"error_code": 0}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
