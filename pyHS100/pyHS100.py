# pyHS100
# Python Library supporting TP-Link Smart Plugs/Switches (HS100/HS110/Hs200)
#
# The communication protocol was reverse engineered by Lubomir Stroetmann and
# Tobias Esser in 'Reverse Engineering the TP-Link HS110'
# https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
#
# This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
# at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
# Stroetmann which is licensed under the Apache License, Version 2.0.
#
# You may obtain a copy of the license at
# http://www.apache.org/licenses/LICENSE-2.0

import datetime
import json
import logging
import socket
import sys

_LOGGER = logging.getLogger(__name__)

# possible device features
FEATURE_ENERGY_METER = 'ENE'
FEATURE_TIMER = 'TIM'

ALL_FEATURES = (FEATURE_ENERGY_METER, FEATURE_TIMER)


class SmartPlug(object):
    """Representation of a TP-Link Smart Switch.

    Usage example when used as library:
    p = SmartPlug("192.168.1.105")
    # print the devices alias
    print(p.alias)
    # change state of plug
    p.state = "OFF"
    p.state = "ON"
    # query and print current state of plug
    print(p.state)
    Note:
    The library references the same structure as defined for the D-Link Switch
    """

    def __init__(self, ip):
        """Create a new SmartPlug instance identified by the IP."""
        self.ip = ip
        self.alias, self.model, self.features = self.identify()

    @property
    def state(self):
        """Get the device state (i.e. ON or OFF)."""
        response = self.get_sysinfo()
        relay_state = response['relay_state']

        if relay_state is None:
            return 'unknown'
        elif relay_state == 0:
            return "OFF"
        elif relay_state == 1:
            return "ON"
        else:
            _LOGGER.warning("Unknown state %s returned" % str(relay_state))
            return 'unknown'

    @state.setter
    def state(self, value):
        """Set device state.
        :type value: str
        :param value: Future state (either ON or OFF)
        """
        if value.upper() == 'ON':
            self.turn_on()

        elif value.upper() == 'OFF':
            self.turn_off()

        else:
            raise TypeError("State %s is not valid." % str(value))

    def get_sysinfo(self):
        """Interrogate the switch"""
        return TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"system":{"get_sysinfo":{}}}'
        )['system']['get_sysinfo']

    def turn_on(self):
        """Turns the switch on

          Return values:
            True on success
            False on failure
        """
        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"system":{"set_relay_state":{"state":1}}}')

        if response["system"]["set_relay_state"]["err_code"] == 0:
            return True

        return False

    def turn_off(self):
        """Turns the switch off

          Return values:
            True on success
            False on failure
        """
        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"system":{"set_relay_state":{"state":0}}}')

        if response["system"]["set_relay_state"]["err_code"] == 0:
            return True

        return False

    @property
    def has_emeter(self):
        return FEATURE_ENERGY_METER in self.features

    def get_emeter_realtime(self):
        """Gets the current energy readings from the switch

          Return values:
            False if command is not successful or the switch doesn't support energy metering
            Dict with the current readings
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"emeter":{"get_realtime":{}}}')

        if response["emeter"]["get_realtime"]["err_code"] != 0:
            return False

        response["emeter"]["get_realtime"].pop('err_code', None)
        return response["emeter"]["get_realtime"]

    def get_emeter_daily(self, year=datetime.datetime.now().year, month=datetime.datetime.now().month):
        """Gets daily statistics for a given month.

          Arguments:
            year (optional): The year for which to retrieve statistics, defaults to current year
            month (optional): The mont for which to retrieve statistics, defaults to current month

          Return values:
            False if command is not successful or the switch doesn't support energy metering
            Dict where the keys represent the days, and the values are the aggregated statistics
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"emeter":{"get_daystat":{"month":' + str(month) + ',"year":' + str(year) + '}}}')

        if response["emeter"]["get_daystat"]["err_code"] != 0:
            return False

        data = dict()

        for i, j in enumerate(response["emeter"]["get_daystat"]["day_list"]):
            if j["energy"] > 0:
                data[j["day"]] = j["energy"]

        return data

    def get_emeter_monthly(self, year=datetime.datetime.now().year):
        """Gets monthly statistics for a given year.

        Arguments:
          year (optional): The year for which to retrieve statistics, defaults to current year

        Return values:
          False if command is not successful or the switch doesn't support energy metering
          Dict - the keys represent the months, the values are the aggregated statistics
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"emeter":{"get_monthstat":{"year":' + str(year) + '}}}')

        if response["emeter"]["get_monthstat"]["err_code"] != 0:
            return False

        data = dict()

        for i, j in enumerate(response["emeter"]["get_monthstat"]["month_list"]):
            if j["energy"] > 0:
                data[j["month"]] = j["energy"]

        return data

    def erase_emeter_stats(self):
        """Erases all statistics.

          Return values:
            True: Success
            False: Failure or not supported by switch
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip, request='{"emeter":{"erase_emeter_stat":null}}')

        if response["emeter"]["erase_emeter_stat"]["err_code"] != 0:
            return False
        else:
            return True

    def current_consumption(self):
        """Get the current power consumption in Watt."""
        if not self.has_emeter:
            return False

        response = self.get_emeter_realtime()

        return response["power"]

    def identify(self):
        """
        Query device information to identify model and featureset

        :return: str model, list of supported features
        """
        sys_info = self.get_sysinfo()

        alias = sys_info['alias']
        model = sys_info["model"]
        features = sys_info['feature'].split(':')

        for feature in features:
            if feature not in ALL_FEATURES:
                _LOGGER.warn('Unknown feature %s on device %s.', feature, model)

        return alias, model, features


class TPLinkSmartHomeProtocol:
    """
    Implementation of the TP-Link Smart Home Protocol

    Encryption/Decryption methods based on the works of
    Lubomir Stroetmann and Tobias Esser

    https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
    https://github.com/softScheck/tplink-smartplug/

    which are licensed under the Apache License, Version 2.0
    http://www.apache.org/licenses/LICENSE-2.0
    """
    IV = 171

    @staticmethod
    def query(host, request, port=9999):
        """
        Request information from a TP-Link SmartHome Device and return the
        response.

        :param host: ip address of the device
        :param port: port on the device (default: 9999)
        :param request: command to send to the device (can be either dict or
        json string)
        :return:
        """
        if isinstance(request, dict):
            request = json.dumps(request)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.send(TPLinkSmartHomeProtocol.encrypt(request))
        buffer = sock.recv(4096)[4:]
        sock.shutdown(socket.SHUT_RDWR)
        sock.close()

        response = TPLinkSmartHomeProtocol.decrypt(buffer)
        return json.loads(response)

    @staticmethod
    def encrypt(request):
        """
        Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext request
        """
        key = TPLinkSmartHomeProtocol.IV
        buffer = ['\0\0\0\0']

        for char in request:
            cipher = key ^ ord(char)
            key = cipher
            buffer.append(chr(cipher))

        ciphertext = ''.join(buffer)
        if sys.version_info.major > 2:
            ciphertext = ciphertext.encode('latin-1')

        return ciphertext

    @staticmethod
    def decrypt(ciphertext):
        """
        Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        key = TPLinkSmartHomeProtocol.IV
        buffer = []

        if sys.version_info.major > 2:
            ciphertext = ciphertext.decode('latin-1')

        for char in ciphertext:
            plain = key ^ ord(char)
            key = ord(char)
            buffer.append(chr(plain))

        plaintext = ''.join(buffer)

        return plaintext
