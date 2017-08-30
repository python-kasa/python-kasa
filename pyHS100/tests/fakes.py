from ..protocol import TPLinkSmartHomeProtocol
from .. import SmartDeviceException
import logging


_LOGGER = logging.getLogger(__name__)

def get_realtime(obj, x):
    return {"current":0.268587,"voltage":125.836131,"power":33.495623,"total":0.199000}

def get_monthstat(obj, x):
    if x["year"] < 2016:
        return {"month_list":[]}

    return {"month_list": [{"year": 2016, "month": 11, "energy": 1.089000}, {"year": 2016, "month": 12, "energy": 1.582000}]}

def get_daystat(obj, x):
    if x["year"] < 2016:
        return {"day_list":[]}

    return {"day_list": [{"year": 2016, "month": 11, "day": 24, "energy": 0.026000},
                  {"year": 2016, "month": 11, "day": 25, "energy": 0.109000}]}

emeter_support = {"get_realtime": get_realtime,
                  "get_monthstat": get_monthstat,
                  "get_daystat": get_daystat,}

def get_realtime_units(obj, x):
    return {"power_mw": 10800}

def get_monthstat_units(obj, x):
    if x["year"] < 2016:
        return {"month_list":[]}

    return {"month_list": [{"year": 2016, "month": 11, "energy_wh": 32}, {"year": 2016, "month": 12, "energy_wh": 16}]}

def get_daystat_units(obj, x):
    if x["year"] < 2016:
        return {"day_list":[]}

    return {"day_list": [{"year": 2016, "month": 11, "day": 24, "energy_wh": 20},
                  {"year": 2016, "month": 11, "day": 25, "energy_wh": 32}]}

emeter_units_support = {"get_realtime": get_realtime_units,
                        "get_monthstat": get_monthstat_units,
                        "get_daystat": get_daystat_units,}

sysinfo_hs100 = {'system': {'get_sysinfo':
                                {'active_mode': 'schedule',
                                 'alias': 'My Smart Plug',
                                 'dev_name': 'Wi-Fi Smart Plug',
                                 'deviceId': '80061E93E28EEBA9FA1929D15C4678C7172A8AF2',
                                 'feature': 'TIM',
                                 'fwId': 'BFF24826FBC561803E49379DBE74FD71',
                                 'hwId': '22603EA5E716DEAEA6642A30BE87AFCA',
                                 'hw_ver': '1.0',
                                 'icon_hash': '',
                                 'latitude': 12.2,
                                 'led_off': 0,
                                 'longitude': 12.2,
                                 'mac': '50:C7:BF:11:22:33',
                                 'model': 'HS100(EU)',
                                 'oemId': '812A90EB2FCF306A993FAD8748024B07',
                                 'on_time': 255419,
                                 'relay_state': 1,
                                 'sw_ver': '1.0.8 Build 151101 Rel.24452',
                                 'type': 'smartplug',
                                 'updating': 0}}}

sysinfo_hs105 = {'system': {'get_sysinfo':
                            {'sw_ver': '1.0.6 Build 160722 Rel.081616',
                             'hw_ver': '1.0', 'type': 'IOT.SMARTPLUGSWITCH',
                             'model': 'HS105(US)',
                             'mac': '50:C7:BF:11:22:33',
                             'dev_name': 'Smart Wi-Fi Plug Mini',
                             'alias': 'TP-LINK_Smart Plug_CF0B',
                             'relay_state': 0,
                             'on_time': 0,
                             'active_mode': 'none',
                             'feature': 'TIM',
                             'updating': 0,
                             'icon_hash': '',
                             'rssi': 33,
                             'led_off': 0,
                             'longitude_i': -12.2,
                             'latitude_i': 12.2,
                             'hwId': '60FF6B258734EA6880E186F8C96DDC61',
                             'fwId': '00000000000000000000000000000000',
                             'deviceId': '800654F32938FCBA8F7327887A38647617',
                             'oemId': 'FFF22CFF774A0B89F7624BFC6F50D5DE'}}}

sysinfo_hs110 = {'system': {'get_sysinfo':
                    {'active_mode': 'schedule',
                    'alias': 'Mobile Plug',
                    'dev_name': 'Wi-Fi Smart Plug With Energy Monitoring',
                    'deviceId': '800654F32938FCBA8F7327887A386476172B5B53',
                    'err_code': 0,
                    'feature': 'TIM:ENE',
                    'fwId': 'E16EB3E95DB6B47B5B72B3FD86FD1438',
                    'hwId': '60FF6B258734EA6880E186F8C96DDC61',
                    'hw_ver': '1.0',
                    'icon_hash': '',
                    'latitude': 12.2,
                    'led_off': 0,
                    'longitude': -12.2,
                    'mac': 'AA:BB:CC:11:22:33',
                    'model': 'HS110(US)',
                    'oemId': 'FFF22CFF774A0B89F7624BFC6F50D5DE',
                    'on_time': 9022,
                    'relay_state': 1,
                    'rssi': -61,
                    'sw_ver': '1.0.8 Build 151113 Rel.24658',
                    'type': 'IOT.SMARTPLUGSWITCH',
                    'updating': 0}
                      },
                 "emeter": emeter_support,
}

sysinfo_hs200 = {'system': {'get_sysinfo': {'active_mode': 'schedule',
                            'alias': 'Christmas Tree Switch',
                            'dev_name': 'Wi-Fi Smart Light Switch',
                            'deviceId': '8006E0D62C90698C6A3EF72944F56DDC17D0DB80',
                            'err_code': 0,
                            'feature': 'TIM',
                            'fwId': 'DB4F3246CD85AA59CAE738A63E7B9C34',
                            'hwId': 'A0E3CC8F5C1166B27A16D56BE262A6D3',
                            'hw_ver': '1.0',
                            'icon_hash': '',
                            'latitude': 12.2,
                            'led_off': 0,
                            'longitude': -12.2,
                            'mac': 'AA:BB:CC:11:22:33',
                            'mic_type': 'IOT.SMARTPLUGSWITCH',
                            'model': 'HS200(US)',
                            'oemId': '4AFE44A41F868FD2340E6D1308D8551D',
                            'on_time': 9586,
                            'relay_state': 1,
                            'rssi': -53,
                            'sw_ver': '1.1.0 Build 160521 Rel.085826',
                            'updating': 0}}
}

sysinfo_lb130 = {'system': {'get_sysinfo':
                    {'active_mode': 'none',
                     'alias': 'Living Room Side Table',
                     'ctrl_protocols': {'name': 'Linkie', 'version': '1.0'},
                     'description': 'Smart Wi-Fi LED Bulb with Color Changing',
                     'dev_state': 'normal',
                     'deviceId': '80123C4640E9FC33A9019A0F3FD8BF5C17B7D9A8',
                     'disco_ver': '1.0',
                     'heapsize': 347000,
                     'hwId': '111E35908497A05512E259BB76801E10',
                     'hw_ver': '1.0',
                     'is_color': 1,
                     'is_dimmable': 1,
                     'is_factory': False,
                     'is_variable_color_temp': 1,
                     'light_state': {'brightness': 100,
                                     'color_temp': 3700,
                                     'hue': 0,
                                     'mode': 'normal',
                                     'on_off': 1,
                                     'saturation': 0},
                     'mic_mac': '50C7BF104865',
                     'mic_type': 'IOT.SMARTBULB',
                     'model': 'LB130(US)',
                     'oemId': '05BF7B3BE1675C5A6867B7A7E4C9F6F7',
                     'preferred_state': [{'brightness': 50,
                                          'color_temp': 2700,
                                          'hue': 0,
                                          'index': 0,
                                          'saturation': 0},
                                         {'brightness': 100,
                                          'color_temp': 0,
                                          'hue': 0,
                                          'index': 1,
                                          'saturation': 75},
                                         {'brightness': 100,
                                          'color_temp': 0,
                                          'hue': 120,
                                          'index': 2,
                                          'saturation': 75},
                                         {'brightness': 100,
                                          'color_temp': 0,
                                          'hue': 240,
                                          'index': 3,
                                          'saturation': 75}],
                     'rssi': -55,
                     'sw_ver': '1.1.2 Build 160927 Rel.111100'}},
                 'smartlife.iot.smartbulb.lightingservice': {'get_light_state':
                                                             {'on_off':1,
                                                              'mode':'normal',
                                                              'hue': 0,
                                                              'saturation': 0,
                                                              'color_temp': 3700,
                                                              'brightness': 100,
                                                              'err_code': 0}},
                 'smartlife.iot.common.emeter': emeter_units_support,
}

sysinfo_lb100 = {'system': {
    'sys_info': {
        'emeter': {
            'err_code': -2001,
            'err_msg': 'Module not support'
        },
        'system': {
            'get_sysinfo': {
                'active_mode': 'none',
                'alias': 'New Light',
                'ctrl_protocols': {
                    'name': 'Linkie',
                    'version': '1.0'
                },
                'description': 'Smart Wi-Fi LED Bulb with Dimmable Light',
                'dev_state': 'normal',
                'deviceId': '8012996ED1F8DA43EFFD58B62BEC5ADE18192F88',
                'disco_ver': '1.0',
                'err_code': 0,
                'heapsize': 340808,
                'hwId': '111E35908497A05512E259BB76801E10',
                'hw_ver': '1.0',
                'is_color': 0,
                'is_dimmable': 1,
                'is_factory': False,
                'is_variable_color_temp': 0,
                'light_state': {
                    'dft_on_state': {
                        'brightness': 50,
                        'color_temp': 2700,
                        'hue': 0,
                        'mode': 'normal',
                        'saturation': 0
                    },
                    'on_off': 0
                },
                'mic_mac': '50C7BF3393F1',
                'mic_type': 'IOT.SMARTBULB',
                'model': 'LB100(US)',
                'oemId': '264E4E97B2D2B086F289AC1F00B90679',
                'preferred_state': [
                    {
                        'brightness': 100,
                        'color_temp': 2700,
                        'hue': 0,
                        'index': 0,
                        'saturation': 0
                    },
                    {
                        'brightness': 75,
                        'color_temp': 2700,
                        'hue': 0,
                        'index': 1,
                        'saturation': 0
                    },
                    {
                        'brightness': 25,
                        'color_temp': 2700,
                        'hue': 0,
                        'index': 2,
                        'saturation': 0
                    },
                    {
                        'brightness': 1,
                        'color_temp': 2700,
                        'hue': 0,
                        'index': 3,
                        'saturation': 0
                    }
                ],
                'rssi': -54,
                'sw_ver': '1.2.3 Build 170123 Rel.100146'
            }
        }
    }
}}

sysinfo_lb110 = {'system': {
    'sys_info':
        {'emeter':
             {'err_code': -2001,
              'err_msg': 'Module not support'},
         'system':
             {'get_sysinfo':
                  {'active_mode': 'schedule',
                   'alias': 'Downstairs Light',
                   'ctrl_protocols':
                       {'name': 'Linkie',
                        'version': '1.0'},
                   'description': 'Smart Wi-Fi LED Bulb '
                                  'with Dimmable Light',
                   'dev_state': 'normal',
                   'deviceId':
                       '80120B3D03E0B639CDF33E3CB1466490187FEF32',
                   'disco_ver': '1.0',
                   'err_code': 0,
                   'heapsize': 309908,
                   'hwId': '111E35908497A05512E259BB76801E10',
                   'hw_ver': '1.0',
                   'is_color': 0,
                   'is_dimmable': 1,
                   'is_factory': False,
                   'is_variable_color_temp': 0,
                   'light_state':
                       {'dft_on_state':
                            {'brightness': 92,
                             'color_temp': 2700,
                             'hue': 0,
                             'mode': 'normal',
                             'saturation': 0},
                        'on_off': 0},
                   'mic_mac': '50C7BF7BE306',
                   'mic_type': 'IOT.SMARTBULB',
                   'model': 'LB110(EU)',
                   'oemId':
                       'A68E15472071CB761E5CCFB388A1D8AE',
                   'preferred_state': [{'brightness': 100,
                                        'color_temp': 2700,
                                        'hue': 0,
                                        'index': 0,
                                        'saturation': 0},
                                       {'brightness': 58,
                                        'color_temp': 2700,
                                        'hue': 0,
                                        'index': 1,
                                        'saturation': 0},
                                       {'brightness': 25,
                                        'color_temp': 2700,
                                        'hue': 0,
                                        'index': 2,
                                        'saturation': 0},
                                       {'brightness': 1,
                                        'color_temp': 2700,
                                        'hue': 0,
                                        'index': 3,
                                        'saturation': 0}],
                   'rssi': -61,
                   'sw_ver': '1.5.5 Build 170623 '
                             'Rel.090105'
                   }
              }
         }
}}

sysinfo_lb120 = {'system':
                     {'sys_info':
                          {'system':
                               {'get_sysinfo':
                                    {'active_mode': 'none',
                                     'alias': 'LB1202',
                                     'ctrl_protocols': {'name': 'Linkie', 'version': '1.0'},
                                     'description': 'Smart Wi-Fi LED Bulb with Tunable White Light',
                                     'dev_state': 'normal',
                                     'deviceId': 'foo',
                                     'disco_ver': '1.0',
                                     'heapsize': 329032,
                                     'hwId': 'foo',
                                     'hw_ver': '1.0',
                                     'is_color': 0,
                                     'is_dimmable': 1,
                                     'is_factory': False,
                                     'is_variable_color_temp': 1,
                                     'light_state': {'dft_on_state': {'brightness': 31,
                                                                      'color_temp': 4100,
                                                                      'hue': 0,
                                                                      'mode': 'normal',
                                                                      'saturation': 0},
                                                     'on_off': 0},
                                     'mic_mac': '50C7BF33937C',
                                     'mic_type': 'IOT.SMARTBULB',
                                     'model': 'LB120(US)',
                                     'oemId': 'foo',
                                     'preferred_state': [{'brightness': 100,
                                                          'color_temp': 3500,
                                                          'hue': 0,
                                                          'index': 0,
                                                          'saturation': 0},
                                                         {'brightness': 50,
                                                          'color_temp': 6500,
                                                          'hue': 0,
                                                          'index': 1,
                                                          'saturation': 0},
                                                         {'brightness': 50,
                                                          'color_temp': 2700,
                                                          'hue': 0,
                                                          'index': 2,
                                                          'saturation': 0},
                                                         {'brightness': 1,
                                                          'color_temp': 2700,
                                                          'hue': 0,
                                                          'index': 3,
                                                          'saturation': 0}],
                                     'rssi': -47,
                                     'sw_ver': '1.4.3 Build 170504 Rel.144921'}
                                }
                           }
                      }
                 }


def error(cls, target, cmd="no-command", msg="default msg"):
    return {target: {cmd: {"err_code": -1323, "msg": msg}}}


def success(target, cmd, res):
    if res:
        res.update({"err_code": 0})
    else:
        res = {"err_code": 0}
    return {target: {cmd: res}}


class FakeTransportProtocol(TPLinkSmartHomeProtocol):
    def __init__(self, sysinfo, invalid=False):
        """ invalid is set only for testing
            to force query() to throw the exception for non-connected """
        proto = FakeTransportProtocol.baseproto
        for target in sysinfo:
            for cmd in sysinfo[target]:
                proto[target][cmd] = sysinfo[target][cmd]
        self.proto = proto
        self.invalid = invalid

    def set_alias(self, x):
        _LOGGER.debug("Setting alias to %s", x["alias"])
        self.proto["system"]["get_sysinfo"]["alias"] = x["alias"]

    def set_relay_state(self, x):
        _LOGGER.debug("Setting relay state to %s", x)
        self.proto["system"]["get_sysinfo"]["relay_state"] = x["state"]

    def set_led_off(self, x):
        _LOGGER.debug("Setting led off to %s", x)
        self.proto["system"]["get_sysinfo"]["led_off"] = x["off"]

    def set_mac(self, x):
        _LOGGER.debug("Setting mac to %s", x)
        self.proto["system"]["get_sysinfo"][""]

    def transition_light_state(self, x):
        _LOGGER.debug("Setting light state to %s", x)
        for key in x:
            self.proto["smartlife.iot.smartbulb.lightingservice"]["get_light_state"][key]=x[key]

    baseproto = {
        "system": { "set_relay_state": set_relay_state,
                    "set_dev_alias": set_alias,
                    "set_led_off": set_led_off,
                    "get_dev_icon": {"icon": None, "hash": None},
                    "set_mac_addr": set_mac,
                    "get_sysinfo": None,
        },
        "emeter": { "get_realtime": None,
                    "get_daystat": None,
                    "get_monthstat": None,
                    "erase_emeter_state": None
        },
        "smartlife.iot.common.emeter": { "get_realtime": None,
                    "get_daystat": None,
                    "get_monthstat": None,
                    "erase_emeter_state": None
        },
        "smartlife.iot.smartbulb.lightingservice": { "get_light_state": None,
                                                    "transition_light_state": transition_light_state,
        },
        "time": { "get_time": { "year": 2017, "month": 1, "mday": 2, "hour": 3, "min": 4, "sec": 5 },
                  "get_timezone": {'zone_str': "test", 'dst_offset': -1, 'index': 12, 'tz_str': "test2" },
                  "set_timezone": None,

        }
    }

    def query(self, host, request, port=9999):
        if self.invalid:
            raise SmartDeviceException("Invalid connection, can't query!")

        proto = self.proto

        target = next(iter(request))
        if target not in proto.keys():
            return error(target, msg="target not found")

        cmd = next(iter(request[target]))
        if cmd not in proto[target].keys():
            return error(target, cmd, msg="command not found")

        params = request[target][cmd]
        _LOGGER.debug("Going to execute {}.{} (params: {}).. ".format(target, cmd, params))

        if callable(proto[target][cmd]):
            res = proto[target][cmd](self, params)
            # verify that change didn't break schema, requires refactoring..
            #TestSmartPlug.sysinfo_schema(self.proto["system"]["get_sysinfo"])
            return success(target, cmd, res)
        elif isinstance(proto[target][cmd], dict):
            return success(target, cmd, proto[target][cmd])
        else:
            raise NotImplementedError("target {} cmd {}".format(target, cmd))
