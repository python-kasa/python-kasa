import logging
import re

from voluptuous import (
    REMOVE_EXTRA,
    All,
    Any,
    Coerce,  # type: ignore
    Invalid,
    Optional,
    Range,
    Schema,
)

from ..protocol import TPLinkSmartHomeProtocol

_LOGGER = logging.getLogger(__name__)


def check_int_bool(x):
    if x != 0 and x != 1:
        raise Invalid(x)
    return x


def check_mac(x):
    if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", x.lower()):
        return x
    raise Invalid(x)


def check_mode(x):
    if x in ["schedule", "none", "count_down"]:
        return x

    raise Invalid(f"invalid mode {x}")


def lb_dev_state(x):
    if x in ["normal"]:
        return x

    raise Invalid(f"Invalid dev_state {x}")


TZ_SCHEMA = Schema(
    {"zone_str": str, "dst_offset": int, "index": All(int, Range(min=0)), "tz_str": str}
)

CURRENT_CONSUMPTION_SCHEMA = Schema(
    Any(
        {
            "voltage": Any(All(float, Range(min=0, max=300)), None),
            "power": Any(Coerce(float, Range(min=0)), None),
            "total": Any(Coerce(float, Range(min=0)), None),
            "current": Any(All(float, Range(min=0)), None),
            "voltage_mv": Any(
                All(float, Range(min=0, max=300000)), int, None
            ),  # TODO can this be int?
            "power_mw": Any(Coerce(float, Range(min=0)), None),
            "total_wh": Any(Coerce(float, Range(min=0)), None),
            "current_ma": Any(
                All(float, Range(min=0)), int, None
            ),  # TODO can this be int?
            "slot_id": Any(Coerce(int, Range(min=0)), None),
        },
        None,
    )
)

# these schemas should go to the mainlib as
# they can be useful when adding support for new features/devices
# as well as to check that faked devices are operating properly.
PLUG_SCHEMA = Schema(
    {
        "active_mode": check_mode,
        "alias": str,
        "dev_name": str,
        "deviceId": str,
        "feature": str,
        "fwId": str,
        "hwId": str,
        "hw_ver": str,
        "icon_hash": str,
        "led_off": check_int_bool,
        "latitude": Any(All(float, Range(min=-90, max=90)), 0, None),
        "latitude_i": Any(
            All(int, Range(min=-900000, max=900000)),
            All(float, Range(min=-900000, max=900000)),
            0,
            None,
        ),
        "longitude": Any(All(float, Range(min=-180, max=180)), 0, None),
        "longitude_i": Any(
            All(int, Range(min=-18000000, max=18000000)),
            All(float, Range(min=-18000000, max=18000000)),
            0,
            None,
        ),
        "mac": check_mac,
        "model": str,
        "oemId": str,
        "on_time": int,
        "relay_state": int,
        "rssi": Any(int, None),  # rssi can also be positive, see #54
        "sw_ver": str,
        "type": str,
        "mic_type": str,
        "updating": check_int_bool,
        # these are available on hs220
        "brightness": int,
        "preferred_state": [
            {"brightness": All(int, Range(min=0, max=100)), "index": int}
        ],
        "next_action": {"type": int},
        "child_num": Optional(Any(None, int)),  # TODO fix hs300 checks
        "children": Optional(list),  # TODO fix hs300
        # TODO some tplink simulator entries contain invalid (mic_mac, _i variants for lat/lon)
        # Therefore we add REMOVE_EXTRA..
        # "INVALIDmac": Optional,
        # "INVALIDlatitude": Optional,
        # "INVALIDlongitude": Optional,
    },
    extra=REMOVE_EXTRA,
)

LIGHT_STATE_SCHEMA = Schema(
    {
        "brightness": All(int, Range(min=0, max=100)),
        "color_temp": int,
        "hue": All(int, Range(min=0, max=360)),
        "mode": str,
        "on_off": check_int_bool,
        "saturation": All(int, Range(min=0, max=100)),
        "dft_on_state": Optional(
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": All(int, Range(min=0, max=9000)),
                "hue": All(int, Range(min=0, max=360)),
                "mode": str,
                "saturation": All(int, Range(min=0, max=100)),
            }
        ),
        "err_code": int,
    }
)

BULB_SCHEMA = PLUG_SCHEMA.extend(
    {
        "ctrl_protocols": Optional(dict),
        "description": Optional(str),  # TODO: LBxxx similar to dev_name
        "dev_state": lb_dev_state,
        "disco_ver": str,
        "heapsize": int,
        "is_color": check_int_bool,
        "is_dimmable": check_int_bool,
        "is_factory": bool,
        "is_variable_color_temp": check_int_bool,
        "light_state": LIGHT_STATE_SCHEMA,
        "preferred_state": [
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": int,
                "hue": All(int, Range(min=0, max=360)),
                "index": int,
                "saturation": All(int, Range(min=0, max=100)),
            }
        ],
    }
)


def get_realtime(obj, x, *args):
    return {
        "current": 0.268587,
        "voltage": 125.836131,
        "power": 33.495623,
        "total": 0.199000,
    }


def get_monthstat(obj, x, *args):
    if x["year"] < 2016:
        return {"month_list": []}

    return {
        "month_list": [
            {"year": 2016, "month": 11, "energy": 1.089000},
            {"year": 2016, "month": 12, "energy": 1.582000},
        ]
    }


def get_daystat(obj, x, *args):
    if x["year"] < 2016:
        return {"day_list": []}

    return {
        "day_list": [
            {"year": 2016, "month": 11, "day": 24, "energy": 0.026000},
            {"year": 2016, "month": 11, "day": 25, "energy": 0.109000},
        ]
    }


emeter_support = {
    "get_realtime": get_realtime,
    "get_monthstat": get_monthstat,
    "get_daystat": get_daystat,
}


def get_realtime_units(obj, x, *args):
    return {"power_mw": 10800}


def get_monthstat_units(obj, x, *args):
    if x["year"] < 2016:
        return {"month_list": []}

    return {
        "month_list": [
            {"year": 2016, "month": 11, "energy_wh": 32},
            {"year": 2016, "month": 12, "energy_wh": 16},
        ]
    }


def get_daystat_units(obj, x, *args):
    if x["year"] < 2016:
        return {"day_list": []}

    return {
        "day_list": [
            {"year": 2016, "month": 11, "day": 24, "energy_wh": 20},
            {"year": 2016, "month": 11, "day": 25, "energy_wh": 32},
        ]
    }


emeter_units_support = {
    "get_realtime": get_realtime_units,
    "get_monthstat": get_monthstat_units,
    "get_daystat": get_daystat_units,
}


emeter_commands = {
    "emeter": emeter_support,
    "smartlife.iot.common.emeter": emeter_units_support,
}


def error(msg="default msg"):
    return {"err_code": -1323, "msg": msg}


def success(res):
    if res:
        res.update({"err_code": 0})
    else:
        res = {"err_code": 0}
    return res


# plugs and bulbs use a different module for time information,
# so we define the contents here to avoid repeating ourselves
TIME_MODULE = {
    "get_time": {
        "year": 2017,
        "month": 1,
        "mday": 2,
        "hour": 3,
        "min": 4,
        "sec": 5,
    },
    "get_timezone": {
        "zone_str": "test",
        "dst_offset": -1,
        "index": 12,
        "tz_str": "test2",
    },
    "set_timezone": None,
}


class FakeTransportProtocol(TPLinkSmartHomeProtocol):
    def __init__(self, info):
        self.discovery_data = info
        self.writer = None
        self.reader = None
        proto = FakeTransportProtocol.baseproto

        for target in info:
            # print("target %s" % target)
            for cmd in info[target]:
                # print("initializing tgt %s cmd %s" % (target, cmd))
                proto[target][cmd] = info[target][cmd]
        # if we have emeter support, we need to add the missing pieces
        for module in ["emeter", "smartlife.iot.common.emeter"]:
            for etype in ["get_realtime", "get_daystat", "get_monthstat"]:
                if (
                    module in info and etype in info[module]
                ):  # if the fixture has the data, use it
                    # print("got %s %s from fixture: %s" % (module, etype, info[module][etype]))
                    proto[module][etype] = info[module][etype]
                else:  # otherwise fall back to the static one
                    dummy_data = emeter_commands[module][etype]
                    # print("got %s %s from dummy: %s" % (module, etype, dummy_data))
                    proto[module][etype] = dummy_data

            # print("initialized: %s" % proto[module])

        self.proto = proto

    def set_alias(self, x, child_ids=None):
        if child_ids is None:
            child_ids = []
        _LOGGER.debug("Setting alias to %s, child_ids: %s", x["alias"], child_ids)
        if child_ids:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                if child["id"] in child_ids:
                    child["alias"] = x["alias"]
        else:
            self.proto["system"]["get_sysinfo"]["alias"] = x["alias"]

    def set_relay_state(self, x, child_ids=None):
        if child_ids is None:
            child_ids = []
        _LOGGER.debug("Setting relay state to %s", x["state"])

        if not child_ids and "children" in self.proto["system"]["get_sysinfo"]:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                child_ids.append(child["id"])

        _LOGGER.info("child_ids: %s", child_ids)
        if child_ids:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                if child["id"] in child_ids:
                    _LOGGER.info("Found %s, turning to %s", child, x["state"])
                    child["state"] = x["state"]
        else:
            self.proto["system"]["get_sysinfo"]["relay_state"] = x["state"]

    def set_led_off(self, x, *args):
        _LOGGER.debug("Setting led off to %s", x)
        self.proto["system"]["get_sysinfo"]["led_off"] = x["off"]

    def set_mac(self, x, *args):
        _LOGGER.debug("Setting mac to %s", x)
        self.proto["system"]["get_sysinfo"]["mac"] = x["mac"]

    def set_hs220_brightness(self, x, *args):
        _LOGGER.debug("Setting brightness to %s", x)
        self.proto["system"]["get_sysinfo"]["brightness"] = x["brightness"]

    def set_hs220_dimmer_transition(self, x, *args):
        _LOGGER.debug("Setting dimmer transition to %s", x)
        brightness = x["brightness"]
        if brightness == 0:
            self.proto["system"]["get_sysinfo"]["relay_state"] = 0
        else:
            self.proto["system"]["get_sysinfo"]["relay_state"] = 1
            self.proto["system"]["get_sysinfo"]["brightness"] = x["brightness"]

    def set_lighting_effect(self, effect, *args):
        _LOGGER.debug("Setting light effect to %s", effect)
        self.proto["system"]["get_sysinfo"]["lighting_effect_state"] = dict(effect)

    def transition_light_state(self, state_changes, *args):
        _LOGGER.debug("Setting light state to %s", state_changes)
        light_state = self.proto["system"]["get_sysinfo"]["light_state"]

        _LOGGER.debug("Current light state: %s", light_state)
        new_state = light_state

        # turn on requested, if we were off, use the dft_on_state as a base
        if state_changes["on_off"] == 1 and not light_state["on_off"]:
            _LOGGER.debug("Bulb was off, using dft_on_state")
            new_state = light_state["dft_on_state"]

        # override the existing settings
        new_state.update(state_changes)

        if (
            not state_changes["on_off"] and "dft_on_state" not in light_state
        ):  # if not already off, pack the data inside dft_on_state
            _LOGGER.debug(
                "Bulb was on and turn_off was requested, saving to dft_on_state"
            )
            new_state = {"dft_on_state": light_state, "on_off": 0}

        _LOGGER.debug("New light state: %s", new_state)
        self.proto["system"]["get_sysinfo"]["light_state"] = new_state

    def set_preferred_state(self, new_state, *args):
        """Implement set_preferred_state."""
        self.proto["system"]["get_sysinfo"]["preferred_state"][
            new_state["index"]
        ] = new_state

    def light_state(self, x, *args):
        light_state = self.proto["system"]["get_sysinfo"]["light_state"]
        # Our tests have light state off, so we simply return the dft_on_state when device is on.
        _LOGGER.debug("reporting light state: %s", light_state)
        # TODO: hack to go around KL430 fixture differences
        if light_state["on_off"] and "dft_on_state" in light_state:
            return light_state["dft_on_state"]
        else:
            return light_state

    baseproto = {
        "system": {
            "set_relay_state": set_relay_state,
            "set_dev_alias": set_alias,
            "set_led_off": set_led_off,
            "get_dev_icon": {"icon": None, "hash": None},
            "set_mac_addr": set_mac,
            "get_sysinfo": None,
        },
        "emeter": {
            "get_realtime": None,
            "get_daystat": None,
            "get_monthstat": None,
            "erase_emeter_state": None,
        },
        "smartlife.iot.common.emeter": {
            "get_realtime": None,
            "get_daystat": None,
            "get_monthstat": None,
            "erase_emeter_state": None,
        },
        "smartlife.iot.smartbulb.lightingservice": {
            "get_light_state": light_state,
            "transition_light_state": transition_light_state,
            "set_preferred_state": set_preferred_state,
        },
        "smartlife.iot.lighting_effect": {
            "set_lighting_effect": set_lighting_effect,
        },
        # lightstrip follows the same payloads but uses different module & method
        "smartlife.iot.lightStrip": {
            "set_light_state": transition_light_state,
            "get_light_state": light_state,
            "set_preferred_state": set_preferred_state,
        },
        "smartlife.iot.common.system": {
            "set_dev_alias": set_alias,
        },
        "time": TIME_MODULE,
        "smartlife.iot.common.timesetting": TIME_MODULE,
        # HS220 brightness, different setter and getter
        "smartlife.iot.dimmer": {
            "set_brightness": set_hs220_brightness,
            "set_dimmer_transition": set_hs220_dimmer_transition,
        },
        "smartlife.iot.LAS": {},
        "smartlife.iot.PIR": {},
    }

    async def query(self, request, port=9999):
        proto = self.proto

        # collect child ids from context
        try:
            child_ids = request["context"]["child_ids"]
            request.pop("context", None)
        except KeyError:
            child_ids = []

        def get_response_for_module(target):
            if target not in proto:
                return error(msg="target not found")

            def get_response_for_command(cmd):
                if cmd not in proto[target]:
                    return error(msg=f"command {cmd} not found")

                params = request[target][cmd]
                _LOGGER.debug(f"Going to execute {target}.{cmd} (params: {params}).. ")

                if callable(proto[target][cmd]):
                    res = proto[target][cmd](self, params, child_ids)
                    _LOGGER.debug("[callable] %s.%s: %s", target, cmd, res)
                    return success(res)
                elif isinstance(proto[target][cmd], dict):
                    res = proto[target][cmd]
                    _LOGGER.debug("[static] %s.%s: %s", target, cmd, res)
                    return success(res)
                else:
                    raise NotImplementedError(f"target {target} cmd {cmd}")

            from collections import defaultdict

            cmd_responses = defaultdict(dict)
            for cmd in request[target]:
                cmd_responses[target][cmd] = get_response_for_command(cmd)

            return cmd_responses

        response = {}
        for target in request:
            response.update(get_response_for_module(target))

        return response
