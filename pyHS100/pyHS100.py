import logging, socket, codecs, json

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
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.ip, self.port))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.ip, self.port))
            on_str = ('0000002ad0f281f88bff9af7d5'
		      'ef94b6c5a0d48bf99cf091e8b7'
		      'c4b0d1a5c0e2d8a381f286e793'
		      'f6d4eedfa2dfa2')
            data = codecs.decode(on_str, 'hex_codec')
            s.send(data)
            s.close()

        elif value.upper() == 'OFF':
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.ip, self.port))
            off_str = ('0000002ad0f281f88bff9af7d5'
                      'ef94b6c5a0d48bf99cf091e8b7'
                      'c4b0d1a5c0e2d8a381f286e793'
                      'f6d4eedea3dea3')
            data = codecs.decode(off_str, 'hex_codec')
            s.send(data)
            s.close()

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
        # The JSON response from the smartplug provide smartplug system information
        sys_info = info["system"]["get_sysinfo"]
        relay_state = sys_info["relay_state"]
        return relay_state
