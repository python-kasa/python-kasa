"""Test data for benchmarks."""


import json

from .original import OriginalTPLinkSmartHomeProtocol

REQUEST = {
    "system": {"get_sysinfo": None},
    "anti_theft": {"get_rules": None, "get_next_action": None},
    "schedule": {
        "get_rules": None,
        "get_next_action": None,
        "get_realtime": None,
        "get_daystat": {"year": 2023, "month": 6},
        "get_monthstat": {"year": 2023},
    },
    "time": {"get_time": None, "get_timezone": None},
    "emeter": {
        "get_realtime": None,
        "get_daystat": {"year": 2023, "month": 6},
        "get_monthstat": {"year": 2023},
    },
}
RESPONSE = {
    "anti_theft": {
        "get_next_action": {"err_code": -2, "err_msg": "member not support"},
        "get_rules": {"enable": 0, "err_code": 0, "rule_list": [], "version": 2},
    },
    "emeter": {
        "get_daystat": {
            "day_list": [{"day": 30, "energy_wh": 0, "month": 6, "year": 2023}],
            "err_code": 0,
        },
        "get_monthstat": {
            "err_code": 0,
            "month_list": [{"energy_wh": 0, "month": 6, "year": 2023}],
        },
        "get_realtime": {
            "current_ma": 0,
            "err_code": 0,
            "power_mw": 0,
            "slot_id": 0,
            "total_wh": 0,
            "voltage_mv": 119390,
        },
    },
    "schedule": {
        "get_daystat": {
            "day_list": [{"day": 30, "month": 6, "time": 3, "year": 2023}],
            "err_code": 0,
        },
        "get_monthstat": {
            "err_code": 0,
            "month_list": [{"month": 6, "time": 3, "year": 2023}],
        },
        "get_next_action": {"err_code": 0, "type": -1},
        "get_realtime": {"err_code": -2, "err_msg": "member not support"},
        "get_rules": {"enable": 1, "err_code": 0, "rule_list": [], "version": 2},
    },
    "system": {
        "get_sysinfo": {
            "alias": "TP-LINK_Power Strip_5C33",
            "child_num": 6,
            "children": [
                {
                    "alias": "Plug 1",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031900",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
                {
                    "alias": "Plug 2",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031901",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
                {
                    "alias": "Plug 3",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031902",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
                {
                    "alias": "Plug 4",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031903",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
                {
                    "alias": "Plug 5",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031904",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
                {
                    "alias": "Plug 6",
                    "id": "8006AF35494E7DB13DDE9B8F40BF2E001E77031905",
                    "next_action": {"type": -1},
                    "on_time": 231,
                    "state": 1,
                },
            ],
            "deviceId": "8006AF35494E7DB13DDE9B8F40BF2E001E770319",
            "err_code": 0,
            "feature": "TIM:ENE",
            "hwId": "955F433CBA24823A248A59AA64571A73",
            "hw_ver": "2.0",
            "latitude_i": 297852,
            "led_off": 0,
            "longitude_i": -954074,
            "mac": "C0:06:C3:42:5C:33",
            "mic_type": "IOT.SMARTPLUGSWITCH",
            "model": "HS300(US)",
            "oemId": "32BD0B21AA9BF8E84737D1DB1C66E883",
            "rssi": -41,
            "status": "new",
            "sw_ver": "1.0.3 Build 201203 Rel.165457",
            "updating": 0,
        }
    },
    "time": {
        "get_time": {
            "err_code": 0,
            "hour": 9,
            "mday": 30,
            "min": 32,
            "month": 6,
            "sec": 54,
            "year": 2023,
        },
        "get_timezone": {"err_code": 0, "index": 13},
    },
}

WIRE_RESPONSE = OriginalTPLinkSmartHomeProtocol.encrypt(json.dumps(RESPONSE))
