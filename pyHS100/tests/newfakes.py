from ..protocol import TPLinkSmartHomeProtocol
from .. import SmartDeviceException
import logging
import re
from voluptuous import Schema, Range, All, Any, Coerce, Invalid, Optional, REMOVE_EXTRA

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

    raise Invalid("invalid mode {}".format(x))


def lb_dev_state(x):
    if x in ["normal"]:
        return x

    raise Invalid("Invalid dev_state {}".format(x))


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
        "latitude": Any(All(float, Range(min=-90, max=90)), None),
        "latitude_i": Any(All(float, Range(min=-90, max=90)), None),
        "longitude": Any(All(float, Range(min=-180, max=180)), None),
        "longitude_i": Any(All(float, Range(min=-180, max=180)), None),
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
        "light_state": {
            "brightness": All(int, Range(min=0, max=100)),
            "color_temp": int,
            "hue": All(int, Range(min=0, max=255)),
            "mode": str,
            "on_off": check_int_bool,
            "saturation": All(int, Range(min=0, max=255)),
            "dft_on_state": Optional(
                {
                    "brightness": All(int, Range(min=0, max=100)),
                    "color_temp": All(int, Range(min=2700, max=9000)),
                    "hue": All(int, Range(min=0, max=255)),
                    "mode": str,
                    "saturation": All(int, Range(min=0, max=255)),
                }
            ),
            "err_code": int,
        },
        "preferred_state": [
            {
                "brightness": All(int, Range(min=0, max=100)),
                "color_temp": int,
                "hue": All(int, Range(min=0, max=255)),
                "index": int,
                "saturation": All(int, Range(min=0, max=255)),
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


def error(target, cmd="no-command", msg="default msg"):
    return {target: {cmd: {"err_code": -1323, "msg": msg}}}


def success(target, cmd, res):
    if res:
        res.update({"err_code": 0})
    else:
        res = {"err_code": 0}
    return {target: {cmd: res}}


class FakeTransportProtocol(TPLinkSmartHomeProtocol):
    def __init__(self, info, invalid=False):
        # TODO remove invalid when removing the old tests.
        proto = FakeTransportProtocol.baseproto
        for target in info:
            # print("target %s" % target)
            for cmd in info[target]:
                # print("initializing tgt %s cmd %s" % (target, cmd))
                proto[target][cmd] = info[target][cmd]
        # if we have emeter support, check for it
        for module in ["emeter", "smartlife.iot.common.emeter"]:
            if module not in info:
                # TODO required for old tests
                continue
            if "get_realtime" in info[module]:
                get_realtime_res = info[module]["get_realtime"]
                # TODO remove when removing old tests
                if callable(get_realtime_res):
                    get_realtime_res = get_realtime_res()
                if (
                    "err_code" not in get_realtime_res
                    or not get_realtime_res["err_code"]
                ):
                    proto[module] = emeter_commands[module]
        self.proto = proto

    def set_alias(self, x, child_ids=[]):
        _LOGGER.debug("Setting alias to %s, child_ids: %s", x["alias"], child_ids)
        if child_ids:
            for child in self.proto["system"]["get_sysinfo"]["children"]:
                if child["id"] in child_ids:
                    child["alias"] = x["alias"]
        else:
            self.proto["system"]["get_sysinfo"]["alias"] = x["alias"]

    def set_relay_state(self, x, child_ids=[]):
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

    def set_alias_old(self, x):
        _LOGGER.debug("Setting alias to %s", x["alias"])
        self.proto["system"]["get_sysinfo"]["alias"] = x["alias"]

    def set_relay_state_old(self, x):
        _LOGGER.debug("Setting relay state to %s", x)
        self.proto["system"]["get_sysinfo"]["relay_state"] = x["state"]

    def set_led_off(self, x, *args):
        _LOGGER.debug("Setting led off to %s", x)
        self.proto["system"]["get_sysinfo"]["led_off"] = x["off"]

    def set_mac(self, x, *args):
        _LOGGER.debug("Setting mac to %s", x)
        self.proto["system"]["get_sysinfo"]["mac"] = x

    def set_hs220_brightness(self, x, *args):
        _LOGGER.debug("Setting brightness to %s", x)
        self.proto["system"]["get_sysinfo"]["brightness"] = x["brightness"]

    def transition_light_state(self, x, *args):
        _LOGGER.debug("Setting light state to %s", x)
        light_state = self.proto["smartlife.iot.smartbulb.lightingservice"][
            "get_light_state"
        ]
        # The required change depends on the light state,
        # exception being turning the bulb on and off

        if "on_off" in x:
            if x["on_off"] and not light_state["on_off"]:  # turning on
                new_state = light_state["dft_on_state"]
                new_state["on_off"] = 1
                self.proto["smartlife.iot.smartbulb.lightingservice"][
                    "get_light_state"
                ] = new_state
            elif not x["on_off"] and light_state["on_off"]:
                new_state = {"dft_on_state": light_state, "on_off": 0}

                self.proto["smartlife.iot.smartbulb.lightingservice"][
                    "get_light_state"
                ] = new_state

            return

        if not light_state["on_off"] and "on_off" not in x:
            light_state = light_state["dft_on_state"]

        _LOGGER.debug("Current state: %s", light_state)
        for key in x:
            light_state[key] = x[key]

    def light_state(self, x, *args):
        light_state = self.proto["smartlife.iot.smartbulb.lightingservice"][
            "get_light_state"
        ]
        # Our tests have light state off, so we simply return the dft_on_state when device is on.
        _LOGGER.info("reporting light state: %s", light_state)
        if light_state["on_off"]:
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
        },
        "time": {
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
        },
        # HS220 brightness, different setter and getter
        "smartlife.iot.dimmer": {"set_brightness": set_hs220_brightness},
    }

    def query(self, host, request, port=9999):
        proto = self.proto

        # collect child ids from context
        try:
            child_ids = request["context"]["child_ids"]
            request.pop("context", None)
        except KeyError:
            child_ids = []

        target = next(iter(request))
        if target not in proto.keys():
            return error(target, msg="target not found")

        cmd = next(iter(request[target]))
        if cmd not in proto[target].keys():
            return error(target, cmd, msg="command not found")

        params = request[target][cmd]
        _LOGGER.debug(
            "Going to execute {}.{} (params: {}).. ".format(target, cmd, params)
        )

        if callable(proto[target][cmd]):
            res = proto[target][cmd](self, params, child_ids)
            _LOGGER.debug("[callable] %s.%s: %s", target, cmd, res)
            # verify that change didn't break schema, requires refactoring..
            # TestSmartPlug.sysinfo_schema(self.proto["system"]["get_sysinfo"])
            return success(target, cmd, res)
        elif isinstance(proto[target][cmd], dict):
            res = proto[target][cmd]
            _LOGGER.debug("[static] %s.%s: %s", target, cmd, res)
            return success(target, cmd, res)
        else:
            raise NotImplementedError("target {} cmd {}".format(target, cmd))
