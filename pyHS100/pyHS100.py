# Parts of this code reuse code and concepts by Lubomir Stroetmann from softScheck GmbH 
# licensed under the Apache License v 2.0.
# Copy of the Apache License can be found at http://www.apache.org/licenses/LICENSE-2.0
# The code from Lubomir Stroetmann is located at http://github.com/softScheck/tplink-smartplug

import logging
import socket
import codecs
import json
import datetime

_LOGGER = logging.getLogger(__name__)


class SmartPlug(object):
    """Class to access TPLink Switch.

    Usage example when used as library:
    p = SmartPlug("192.168.1.105")
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
        self.port = 9999
        self._error_report = False
        self.model = self._identify_model()

    @property
    def state(self):
        """Get the device state (i.e. ON or OFF)."""
        response = self.hs100_status()
        if response is None:
            return 'unknown'
        elif response == 0:
            return "OFF"
        elif response == 1:
            return "ON"
        else:
            _LOGGER.warning("Unknown state %s returned" % str(response))
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

    def hs100_status(self):
        """Query HS100 for relay status."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip, self.port))
        skip = 4
        code = 171
        response = ""
        query_str = ('00000023d0f0d2a1d8abdfbad7'
                     'f5cfb494b6d1b4c09fec95e68f'
                     'e187e8caf09eeb87ebcbb696eb')
        data = codecs.decode(query_str, 'hex_codec')
        s.send(data)
        reply = s.recv(4096)
        s.shutdown(1)
        s.close()

        for value in reply:
            if skip > 0:
                skip = skip - 1
            else:
                change = (value ^ code)
                response = response + chr(change)
                code = value

        info = json.loads(response)
        # info is reserved for future expansion.
        sys_info = info["system"]["get_sysinfo"]
        relay_state = sys_info["relay_state"]
        return relay_state

    def get_info(self):
      """Interrogate the switch"""
      return self._send_command('{"system":{"get_sysinfo":{}}}')

    def turn_on(self):
      """Turns the switch on

        Return values:
          True on success
          False on failure
      """
      response = self._send_command('{"system":{"set_relay_state":{"state":1}}}')

      if response["system"]["set_relay_state"]["err_code"] == 0:
        return True

      return False

    def turn_off(self):
      """Turns the switch off

        Return values:
          True on success
          False on failure
      """
      response = self._send_command('{"system":{"set_relay_state":{"state":0}}}')

      if response["system"]["set_relay_state"]["err_code"] == 0:
        return True

      return False
      
    def get_emeter_realtime(self):
      """Gets the current energy readings from the switch

        Return values:
          False if command is not successful or the switch doesn't support energy metering
          Dict with the current readings
      """
      if self.model == 100:
        return False

      response = self._send_command('{"emeter":{"get_realtime":{}}}')

      if response["emeter"]["get_realtime"]["err_code"] != 0:
        return False

      response["emeter"]["get_realtime"].pop('err_code', None)
      return response["emeter"]["get_realtime"]

    def get_emeter_daily(self, year = datetime.datetime.now().year, month = datetime.datetime.now().month):
      """Gets daily statistics for a given month.
        
        Arguments:
          year (optional): The year for which to retrieve statistics, defaults to current year
          month (optional): The mont for which to retrieve statistics, defaults to current month

        Return values:
          False if command is not successful or the switch doesn't support energy metering
          Dict where the keys represent the days, and the values are the aggregated statistics
      """
      if self.model == 100:
        return False

      response = self._send_command('{"emeter":{"get_daystat":{"month":' + str(month) + ',"year":' + str(year) + '}}}')

      if response["emeter"]["get_daystat"]["err_code"] != 0:
        return False

      data = dict()

      for i, j in enumerate(response["emeter"]["get_daystat"]["day_list"]):
        if j["energy"] > 0:
          data[j["day"]] = j["energy"]

      return data

    def get_emeter_monthly(self, year = datetime.datetime.now().year):
      """Gets monthly statistics for a given year.

        Arguments:
          year (optional): The year for which to retrieve statistics, defaults to current year

        Return values:
          False if command is not successful or the switch doesn't support energy metering
          Dict - the keys represent the months, the values are the aggregated statistics
      """
      if self.model == 100:
        return False

      response = self._send_command('{"emeter":{"get_monthstat":{"year":' + str(year) + '}}}')

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

      if self.model == 100:
        return False

      response = self._send_command('{"emeter":{"erase_emeter_stat":null}}')

      if response["emeter"]["erase_emeter_stat"]["err_code"] != 0:
        return False
      else:
        return True

    def current_consumption(self):
      """Get the current power consumption in Watt."""

      response = self.get_emeter_realtime()

      return response["power"]

    def _encrypt(self, string):
      """Encrypts a command."""
      key = 171
      result = "\0\0\0\0"
      for i in string: 
        a = key ^ ord(i)
        key = a
        result += chr(a)
      return result

    def _decrypt(self, string):
      """Decrypts a command."""
      key = 171 
      result = ""
      for i in string: 
        a = key ^ ord(i)
        key = ord(i) 
        result += chr(a)
      return result

    def _send_command(self, command):
      """Sends a command to the switch.
          
        Accepts one argument - the command as a string
        
        Return values:
          The decrypted JSON
      """
      s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      s.connect((self.ip, self.port))
      s.send(self._encrypt(command))
      response = self._decrypt(s.recv(4096)[4:])
      s.close()

      return json.loads(response)

    def _identify_model(self):
      """Query sysinfo and determine model"""
      sys_info = self.get_info()

      if sys_info["system"]["get_sysinfo"]["model"][:5] == 'HS100':
        model = 100
      elif sys_info["system"]["get_sysinfo"]["model"][:5] == 'HS110':
        model = 110

      return model