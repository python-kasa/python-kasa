"""SmartRequest helper classes and functions for new SMART/TAPO devices.

List of known requests with associated parameter classes.

Other requests that are known but not currently implemented
or tested are:

get_child_device_component_list
get_child_device_list
control_child
get_device_running_info - seems to be a subset of get_device_info

get_tss_info
get_raw_dvi
get_homekit_info

fw_download

sync_env
account_sync

device_reset
close_device_ble
heart_beat

"""

import logging
from dataclasses import asdict, dataclass
from typing import List, Optional, Union

_LOGGER = logging.getLogger(__name__)


class SmartRequest:
    """Class to represent a smart protocol request."""

    def __init__(self, method_name: str, params: Optional["SmartRequestParams"] = None):
        self.method_name = method_name
        if params:
            self.params = params.to_dict()
        else:
            self.params = None

    def __repr__(self):
        return f"SmartRequest({self.method_name})"

    def to_dict(self):
        """Return the request as a dict suitable for passing to query()."""
        return {self.method_name: self.params}

    @dataclass
    class SmartRequestParams:
        """Base class for Smart request params.

        The to_dict() method of this class omits null values which
        is required by the devices.
        """

        def to_dict(self):
            """Return the params as a dict with values of None ommited."""
            return asdict(
                self, dict_factory=lambda x: {k: v for (k, v) in x if v is not None}
            )

    @dataclass
    class DeviceOnParams(SmartRequestParams):
        """Get Rules Params."""

        device_on: bool

    @dataclass
    class GetRulesParams(SmartRequestParams):
        """Get Rules Params."""

        start_index: int = 0

    @dataclass
    class GetTriggerLogsParams(SmartRequestParams):
        """Trigger Logs params."""

        page_size: int = 5
        start_id: int = 0

    @dataclass
    class LedStatusParams(SmartRequestParams):
        """LED Status params."""

        led_rule: Optional[str] = None

        @staticmethod
        def from_bool(state: bool):
            """Set the led_rule from the state."""
            rule = "always" if state else "never"
            return SmartRequest.LedStatusParams(led_rule=rule)

    @dataclass
    class LightInfoParams(SmartRequestParams):
        """LightInfo params."""

        brightness: Optional[int] = None
        color_temp: Optional[int] = None
        hue: Optional[int] = None
        saturation: Optional[int] = None

    @dataclass
    class DynamicLightEffectParams(SmartRequestParams):
        """LightInfo params."""

        enable: bool
        id: Optional[str] = None

    @staticmethod
    def get_raw_request(
        method: str, params: Optional[SmartRequestParams] = None
    ) -> "SmartRequest":
        """Send a raw request to the device."""
        return SmartRequest(method, params)

    @staticmethod
    def component_nego() -> "SmartRequest":
        """Get quick setup component info."""
        return SmartRequest("component_nego")

    @staticmethod
    def get_device_info() -> "SmartRequest":
        """Get device info."""
        return SmartRequest("get_device_info")

    @staticmethod
    def get_device_usage() -> "SmartRequest":
        """Get device usage."""
        return SmartRequest("get_device_usage")

    @staticmethod
    def device_info_list() -> List["SmartRequest"]:
        """Get device info list."""
        return [
            SmartRequest.get_device_info(),
            SmartRequest.get_device_usage(),
        ]

    @staticmethod
    def get_auto_update_info() -> "SmartRequest":
        """Get auto update info."""
        return SmartRequest("get_auto_update_info")

    @staticmethod
    def firmware_info_list() -> List["SmartRequest"]:
        """Get info list."""
        return [
            SmartRequest.get_auto_update_info(),
            SmartRequest.get_raw_request("get_fw_download_state"),
            SmartRequest.get_raw_request("get_latest_fw"),
        ]

    @staticmethod
    def qs_component_nego() -> "SmartRequest":
        """Get quick setup component info."""
        return SmartRequest("qs_component_nego")

    @staticmethod
    def get_device_time() -> "SmartRequest":
        """Get device time."""
        return SmartRequest("get_device_time")

    @staticmethod
    def get_wireless_scan_info() -> "SmartRequest":
        """Get wireless scan info."""
        return SmartRequest("get_wireless_scan_info")

    @staticmethod
    def get_schedule_rules(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get schedule rules."""
        return SmartRequest(
            "get_schedule_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_next_event(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get next scheduled event."""
        return SmartRequest("get_next_event", params or SmartRequest.GetRulesParams())

    @staticmethod
    def schedule_info_list() -> List["SmartRequest"]:
        """Get schedule info list."""
        return [
            SmartRequest.get_schedule_rules(),
            SmartRequest.get_next_event(),
        ]

    @staticmethod
    def get_countdown_rules(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get countdown rules."""
        return SmartRequest(
            "get_countdown_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_antitheft_rules(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get antitheft rules."""
        return SmartRequest(
            "get_antitheft_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_led_info(params: Optional[LedStatusParams] = None) -> "SmartRequest":
        """Get led info."""
        return SmartRequest("get_led_info", params or SmartRequest.LedStatusParams())

    @staticmethod
    def get_auto_off_config(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get auto off config."""
        return SmartRequest(
            "get_auto_off_config", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def get_delay_action_info() -> "SmartRequest":
        """Get delay action info."""
        return SmartRequest("get_delay_action_info")

    @staticmethod
    def auto_off_list() -> List["SmartRequest"]:
        """Get energy usage."""
        return [
            SmartRequest.get_auto_off_config(),
            SmartRequest.get_delay_action_info(),  # May not live here
        ]

    @staticmethod
    def get_energy_usage() -> "SmartRequest":
        """Get energy usage."""
        return SmartRequest("get_energy_usage")

    @staticmethod
    def energy_monitoring_list() -> List["SmartRequest"]:
        """Get energy usage."""
        return [
            SmartRequest("get_energy_usage"),
            SmartRequest.get_raw_request("get_electricity_price_config"),
        ]

    @staticmethod
    def get_current_power() -> "SmartRequest":
        """Get current power."""
        return SmartRequest("get_current_power")

    @staticmethod
    def power_protection_list() -> List["SmartRequest"]:
        """Get power protection info list."""
        return [
            SmartRequest.get_current_power(),
            SmartRequest.get_raw_request("get_max_power"),
            SmartRequest.get_raw_request("get_protection_power"),
        ]

    @staticmethod
    def get_preset_rules(params: Optional[GetRulesParams] = None) -> "SmartRequest":
        """Get preset rules."""
        return SmartRequest("get_preset_rules", params or SmartRequest.GetRulesParams())

    @staticmethod
    def get_auto_light_info() -> "SmartRequest":
        """Get auto light info."""
        return SmartRequest("get_auto_light_info")

    @staticmethod
    def get_dynamic_light_effect_rules(
        params: Optional[GetRulesParams] = None
    ) -> "SmartRequest":
        """Get dynamic light effect rules."""
        return SmartRequest(
            "get_dynamic_light_effect_rules", params or SmartRequest.GetRulesParams()
        )

    @staticmethod
    def set_device_on(params: DeviceOnParams) -> "SmartRequest":
        """Set device on state."""
        return SmartRequest("set_device_info", params)

    @staticmethod
    def set_light_info(params: LightInfoParams) -> "SmartRequest":
        """Set color temperature."""
        return SmartRequest("set_device_info", params)

    @staticmethod
    def set_dynamic_light_effect_rule_enable(
        params: DynamicLightEffectParams
    ) -> "SmartRequest":
        """Enable dynamic light effect rule."""
        return SmartRequest("set_dynamic_light_effect_rule_enable", params)

    @staticmethod
    def get_component_info_requests(component_nego_response) -> List["SmartRequest"]:
        """Get a list of requests based on the component info response."""
        request_list = []
        for component in component_nego_response["component_list"]:
            if requests := COMPONENT_REQUESTS.get(component["id"]):
                request_list.extend(requests)
        return request_list

    @staticmethod
    def _create_request_dict(
        smart_request: Union["SmartRequest", List["SmartRequest"]]
    ) -> dict:
        """Create request dict to be passed to SmartProtocol.query()."""
        if isinstance(smart_request, list):
            request = {}
            for sr in smart_request:
                request[sr.method_name] = sr.params
        else:
            request = smart_request.to_dict()
        return request


COMPONENT_REQUESTS = {
    "device": SmartRequest.device_info_list(),
    "firmware": SmartRequest.firmware_info_list(),
    "quick_setup": [SmartRequest.qs_component_nego()],
    "inherit": [SmartRequest.get_raw_request("get_inherit_info")],
    "time": [SmartRequest.get_device_time()],
    "wireless": [SmartRequest.get_wireless_scan_info()],
    "schedule": SmartRequest.schedule_info_list(),
    "countdown": [SmartRequest.get_countdown_rules()],
    "antitheft": [SmartRequest.get_antitheft_rules()],
    "account": None,
    "synchronize": None,  # sync_env
    "sunrise_sunset": None,  # for schedules
    "led": [SmartRequest.get_led_info()],
    "cloud_connect": [SmartRequest.get_raw_request("get_connect_cloud_state")],
    "iot_cloud": None,
    "device_local_time": None,
    "default_states": None,  # in device_info
    "auto_off": [SmartRequest.get_auto_off_config()],
    "localSmart": None,
    "energy_monitoring": SmartRequest.energy_monitoring_list(),
    "power_protection": SmartRequest.power_protection_list(),
    "current_protection": None,  # overcurrent in device_info
    "matter": None,
    "preset": [SmartRequest.get_preset_rules()],
    "brightness": None,  # in device_info
    "color": None,  # in device_info
    "color_temperature": None,  # in device_info
    "auto_light": [SmartRequest.get_auto_light_info()],
    "light_effect": [SmartRequest.get_dynamic_light_effect_rules()],
    "bulb_quick_control": None,
    "on_off_gradually": [SmartRequest.get_raw_request("get_on_off_gradually_info")],
    "light_strip": None,
    "light_strip_lighting_effect": [
        SmartRequest.get_raw_request("get_lighting_effect")
    ],
    "music_rhythm": None,  # music_rhythm_enable in device_info
    "segment": [SmartRequest.get_raw_request("get_device_segment")],
    "segment_effect": [SmartRequest.get_raw_request("get_segment_effect_rule")],
}
