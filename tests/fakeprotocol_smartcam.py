from __future__ import annotations

import copy
from json import loads as json_loads
from typing import Any

from kasa import Credentials, DeviceConfig, SmartProtocol
from kasa.protocols.smartcamprotocol import SmartCamProtocol
from kasa.smartcam.smartcamchild import CHILD_INFO_FROM_PARENT, SmartCamChild
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
        get_child_fixtures=True,
        verbatim=False,
        components_not_included=False,
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
            # We don't need to get the child fixtures if testing things like
            # lists
            if get_child_fixtures:
                self.child_protocols = FakeSmartTransport._get_child_protocols(
                    self.info, self.fixture_name, "getChildDeviceList", self.verbatim
                )
        else:
            self.info = info

        self.list_return_size = list_return_size

        # Setting this flag allows tests to create dummy transports without
        # full fixture info for testing specific cases like list handling etc
        self.components_not_included = (components_not_included,)
        if not components_not_included:
            self.components = {
                comp["name"]: comp["version"]
                for comp in self.info["getAppComponentList"]["app_component"][
                    "app_component_list"
                ]
            }

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
        cifp = info.get(CHILD_INFO_FROM_PARENT)

        for key in set_keys[:-1]:
            info = info[key]
        info[set_keys[-1]] = value

        if (
            cifp
            and set_keys[0] == "getDeviceInfo"
            and (
                child_info_parent_key
                := FakeSmartCamTransport.CHILD_INFO_SETTER_MAP.get(set_keys[-1])
            )
        ):
            cifp[child_info_parent_key] = value

    CHILD_INFO_SETTER_MAP = {
        "device_alias": "alias",
    }

    FIXTURE_MISSING_MAP = {
        "getMatterSetupInfo": (
            "matter",
            {
                "setup_code": "00000000000",
                "setup_payload": "00:0000000-0000.00.000",
            },
        ),
        "getSupportChildDeviceCategory": (
            "childQuickSetup",
            {
                "device_category_list": [
                    {"category": "ipcamera"},
                    {"category": "subg.trv"},
                    {"category": "subg.trigger"},
                    {"category": "subg.plugswitch"},
                ]
            },
        ),
        "getScanChildDeviceList": (
            "childQuickSetup",
            {
                "child_device_list": [
                    {
                        "device_id": "0000000000000000000000000000000000000000",
                        "category": "subg.trigger.button",
                        "device_model": "S200B",
                        "name": "I01BU0tFRF9OQU1FIw====",
                    }
                ],
                "scan_wait_time": 55,
                "scan_status": "scanning",
            },
        ),
    }
    # Setters for when there's not a simple mapping of setters to getters
    SETTERS = {
        ("system", "sys", "dev_alias"): [
            "getDeviceInfo",
            "device_info",
            "basic_info",
            "device_alias",
        ],
    }

    def _hub_remove_device(self, info, params):
        """Remove hub device."""
        items_to_remove = [dev["device_id"] for dev in params["child_device_list"]]
        children = info["getChildDeviceList"]["child_device_list"]
        new_children = [
            dev for dev in children if dev["device_id"] not in items_to_remove
        ]
        info["getChildDeviceList"]["child_device_list"] = new_children

        return {"result": {}, "error_code": 0}

    @staticmethod
    def _get_second_key(request_dict: dict[str, Any]) -> str:
        assert len(request_dict) == 2, (
            f"Unexpected dict {request_dict}, should be length 2"
        )
        it = iter(request_dict)
        next(it, None)
        return next(it)

    def get_child_device_queries(self, method, params):
        return self._get_method_from_info(method, params)

    def _get_method_from_info(self, method, params):
        result = copy.deepcopy(self.info[method])
        if "start_index" in result and "sum" in result:
            list_key = next(
                iter([key for key in result if isinstance(result[key], list)])
            )
            assert isinstance(params, dict)
            module_name = next(iter(params))

            start_index = (
                start_index
                if (
                    params
                    and module_name
                    and (start_index := params[module_name].get("start_index"))
                )
                else 0
            )

            result[list_key] = result[list_key][
                start_index : start_index + self.list_return_size
            ]
        return {"result": result, "error_code": 0}

    async def _send_request(self, request_dict: dict):
        method = request_dict["method"]

        info = self.info
        if method == "connectAp":
            if self.verbatim:
                return {"error_code": -1}
            return {"result": {}, "error_code": 0}
        if method == "scanApList":
            if method in info:
                result = self._get_method_from_info(method, request_dict.get("params"))
                if not self.verbatim:
                    scan = (
                        result.get("result", {}).get("onboarding", {}).get("scan", {})
                    )
                    ap_list = scan.get("ap_list")
                    if isinstance(ap_list, list) and not any(
                        ap.get("ssid") == "FOOBAR" for ap in ap_list
                    ):
                        ap_list.append(
                            {
                                "ssid": "FOOBAR",
                                "auth": 3,
                                "encryption": 3,
                                "rssi": -40,
                                "bssid": "00:00:00:00:00:00",
                            }
                        )
                return result
            if self.verbatim:
                return {"error_code": -1}
            return {
                "result": {
                    "onboarding": {
                        "scan": {
                            "publicKey": "",
                            "ap_list": [
                                {
                                    "ssid": "FOOBAR",
                                    "auth": 3,
                                    "encryption": 3,
                                    "rssi": -40,
                                    "bssid": "00:00:00:00:00:00",
                                }
                            ],
                        }
                    }
                },
                "error_code": 0,
            }
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
                    updates = {
                        k: v for k, v in val.items() if k in info.get(get_method, {})
                    }
                    if len(updates) != len(val):
                        # All keys to update must already be in the getter
                        return {"error_code": -1}
                    info[get_method] = {**info[get_method], **updates}

                    break
                for skey, sval in skey_val.items():
                    section_key = skey
                    section_value = sval
                    if setter_keys := self.SETTERS.get((module, section, section_key)):
                        self._get_param_set_value(info, setter_keys, section_value)
                    elif (
                        section_data := info.get(get_method, {})
                        .get(module, {})
                        .get(section, {})
                    ) and section_key in section_data:
                        section_data[section_key] = section_value
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
        elif method == "removeChildDeviceList":
            return self._hub_remove_device(info, request_dict["params"]["childControl"])
        # actions
        elif method in [
            "addScanChildDeviceList",
            "startScanChildDevice",
            "motorMoveToPreset",
            "addMotorPostion",  # Note: API has typo in method name
        ]:
            return {"result": {}, "error_code": 0}

        # smartcam child devices do not make requests for getDeviceInfo as they
        # get updated from the parent's query. If this is being called from a
        # child it must be because the fixture has been created directly on the
        # child device with a dummy parent. In this case return the child info
        # from parent that's inside the fixture.
        if (
            not self.verbatim
            and method == "getDeviceInfo"
            and (cifp := info.get(CHILD_INFO_FROM_PARENT))
        ):
            mapped = SmartCamChild._map_child_info_from_parent(cifp)
            result = {"device_info": {"basic_info": mapped}}
            return {"result": result, "error_code": 0}

        # These methods are handled in get_child_device_query so it can be
        # patched for tests to simulate dynamic devices.
        if (
            method in ("getChildDeviceList", "getChildDeviceComponentList")
            and method in info
        ):
            params = request_dict.get("params")
            return self.get_child_device_queries(method, params)

        if method in info:
            params = request_dict.get("params")
            return self._get_method_from_info(method, params)

        if self.verbatim:
            return {"error_code": -1}

        if (
            # FIXTURE_MISSING is for service calls not in place when
            # SMART fixtures started to be generated
            missing_result := self.FIXTURE_MISSING_MAP.get(method)
        ) and missing_result[0] in self.components:
            # Copy to info so it will work with update methods
            info[method] = copy.deepcopy(missing_result[1])
            result = copy.deepcopy(info[method])
            return {"result": result, "error_code": 0}

        return {"error_code": -1}

    async def close(self) -> None:
        pass

    async def reset(self) -> None:
        pass
