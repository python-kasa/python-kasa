"""
pyHS100
Python library supporting TP-Link Smart Plugs/Switches (HS100/HS110/Hs200).

The communication protocol was reverse engineered by Lubomir Stroetmann and
Tobias Esser in 'Reverse Engineering the TP-Link HS110':
https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/

This library reuses codes and concepts of the TP-Link WiFi SmartPlug Client
at https://github.com/softScheck/tplink-smartplug, developed by Lubomir
Stroetmann which is licensed under the Apache License, Version 2.0.

You may obtain a copy of the license at
http://www.apache.org/licenses/LICENSE-2.0
"""

import datetime
import json
import logging
import socket
import sys

_LOGGER = logging.getLogger(__name__)


class SmartPlug:
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
    # switch states
    SWITCH_STATE_ON = 'ON'
    SWITCH_STATE_OFF = 'OFF'
    SWITCH_STATE_UNKNOWN = 'UNKNOWN'

    # possible device features
    FEATURE_ENERGY_METER = 'ENE'
    FEATURE_TIMER = 'TIM'

    ALL_FEATURES = (FEATURE_ENERGY_METER, FEATURE_TIMER)

    def __init__(self, ip_address):
        """
        Create a new SmartPlug instance, identified through its IP address.

        :param ip_address: ip address on which the device listens
        """
        socket.inet_pton(socket.AF_INET, ip_address)
        self.ip_address = ip_address

        self.alias, self.model, self.features = self.identify()

    @property
    def state(self):
        """
        Retrieve the switch state

        :returns: one of
                  SWITCH_STATE_ON
                  SWITCH_STATE_OFF
                  SWITCH_STATE_UNKNOWN
        """
        response = self.get_sysinfo()
        relay_state = response['relay_state']

        if relay_state == 0:
            return SmartPlug.SWITCH_STATE_OFF
        elif relay_state == 1:
            return SmartPlug.SWITCH_STATE_ON
        else:
            _LOGGER.warning("Unknown state %s returned.", relay_state)
            return SmartPlug.SWITCH_STATE_UNKNOWN

    @state.setter
    def state(self, value):
        """
        Set the new switch state

        :param value: one of
                    SWITCH_STATE_ON
                    SWITCH_STATE_OFF
        :return: True if new state was successfully set
                 False if an error occured
        """
        if value.upper() == SmartPlug.SWITCH_STATE_ON:
            self.turn_on()
        elif value.upper() == SmartPlug.SWITCH_STATE_OFF:
            self.turn_off()
        else:
            raise ValueError("State %s is not valid.", value)

    def get_sysinfo(self):
        """
        Retrieve system information.

        :return: dict sysinfo
        """
        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'system': {'get_sysinfo': {}}}
        )['system']['get_sysinfo']

        if response['err_code'] != 0:
            return False

        return response

    def turn_on(self):
        """
        Turn the switch on.

        :return: True on success
        :raises ProtocolError when device responds with err_code != 0
        """
        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'system': {'set_relay_state': {'state': 1}}}
        )['system']['set_relay_state']

        if response['err_code'] != 0:
            return False

        return True

    def turn_off(self):
        """
        Turn the switch off.

        :return: True on success
                 False on error
        """
        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'system': {'set_relay_state': {'state': 0}}}
        )['system']['set_relay_state']

        if response['err_code'] != 0:
            return False

        return True

    @property
    def has_emeter(self):
        """
        Checks feature list for energey meter support.

        :return: True if energey meter is available
                 False if energymeter is missing
        """
        return SmartPlug.FEATURE_ENERGY_METER in self.features

    def get_emeter_realtime(self):
        """
        Retrive current energy readings from device.

        :returns: dict with current readings
                  False if device has no energy meter or error occured
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address, request={'emeter': {'get_realtime': {}}}
        )['emeter']['get_realtime']

        if response['err_code'] != 0:
            return False

        del response['err_code']

        return response

    def get_emeter_daily(self, year=None, month=None):
        """
        Retrieve daily statistics for a given month

        :param year: year for which to retrieve statistics (default: this year)
        :param month: month for which to retrieve statistcs (default: this
                      month)
        :return: dict: mapping of day of month to value
                 False if device has no energy meter or error occured
        """
        if not self.has_emeter:
            return False

        if year is None:
            year = datetime.datetime.now().year
        if month is None:
            month = datetime.datetime.now().month

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'emeter': {'get_daystat': {'month': str(month),
                                                'year': str(year)}}}
        )['emeter']['get_daystat']

        if response['err_code'] != 0:
            return False

        return {entry['day']: entry['energy']
                for entry in response['day_list']}

    def get_emeter_monthly(self, year=datetime.datetime.now().year):
        """
        Retrieve monthly statistics for a given year.

        :param year: year for which to retrieve statistics (default: this year)
        :return: dict: mapping of month to value
                 False if device has no energy meter or error occured
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'emeter': {'get_monthstat': {'year': str(year)}}}
        )['emeter']['get_monthstat']

        if response['err_code'] != 0:
            return False

        return {entry['month']: entry['energy']
                for entry in response['month_list']}

    def erase_emeter_stats(self):
        """
        Erase energy meter statistics

        :return: True if statistics were deleted
                 False if device has no energy meter or error occured
        """
        if not self.has_emeter:
            return False

        response = TPLinkSmartHomeProtocol.query(
            host=self.ip_address,
            request={'emeter': {'erase_emeter_stat': None}}
        )['emeter']['erase_emeter_stat']

        return response['err_code'] == 0

    def current_consumption(self):
        """
        Get the current power consumption in Watt.

        :return: the current power consumption in Watt.
                 False if device has no energy meter of error occured.
        """
        if not self.has_emeter:
            return False

        response = self.get_emeter_realtime()

        return response['power']

    def identify(self):
        """
        Query device information to identify model and featureset

        :return: str model, list of supported features
        """
        sys_info = self.get_sysinfo()

        alias = sys_info['alias']
        model = sys_info['model']
        features = sys_info['feature'].split(':')

        for feature in features:
            if feature not in SmartPlug.ALL_FEATURES:
                _LOGGER.warning("Unknown feature %s on device %s.",
                                feature, model)

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
    initialization_vector = 171

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
        key = TPLinkSmartHomeProtocol.initialization_vector
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
        key = TPLinkSmartHomeProtocol.initialization_vector
        buffer = []

        if sys.version_info.major > 2:
            ciphertext = ciphertext.decode('latin-1')

        for char in ciphertext:
            plain = key ^ ord(char)
            key = ord(char)
            buffer.append(chr(plain))

        plaintext = ''.join(buffer)

        return plaintext
