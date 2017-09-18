import socket
import logging
import json
from typing import Dict

from pyHS100 import TPLinkSmartHomeProtocol, SmartDevice, SmartPlug, SmartBulb

_LOGGER = logging.getLogger(__name__)


class Discover:
    @staticmethod
    def discover(protocol: TPLinkSmartHomeProtocol = None,
                 port: int = 9999,
                 timeout: int = 3) -> Dict[str, SmartDevice]:
        """
        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.

        :param protocol: Protocol implementation to use
        :param timeout: How long to wait for responses, defaults to 5
        :param port: port to send broadcast messages, defaults to 9999.
        :rtype: dict
        :return: Array of json objects {"ip", "port", "sys_info"}
        """
        if protocol is None:
            protocol = TPLinkSmartHomeProtocol()

        discovery_query = {"system": {"get_sysinfo": None},
                           "emeter": {"get_realtime": None}}
        target = "255.255.255.255"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        req = json.dumps(discovery_query)
        _LOGGER.debug("Sending discovery to %s:%s", target, port)

        encrypted_req = protocol.encrypt(req)
        sock.sendto(encrypted_req[4:], (target, port))

        devices = {}
        _LOGGER.debug("Waiting %s seconds for responses...", timeout)

        try:
            while True:
                data, addr = sock.recvfrom(4096)
                ip, port = addr
                info = json.loads(protocol.decrypt(data))
                if "system" in info and "get_sysinfo" in info["system"]:
                    sysinfo = info["system"]["get_sysinfo"]
                    if "type" in sysinfo:
                        type = sysinfo["type"]
                    elif "mic_type" in sysinfo:
                        type = sysinfo["mic_type"]
                    else:
                        _LOGGER.error("Unable to find the device type field!")
                        type = "UNKNOWN"
                else:
                    _LOGGER.error("No 'system' nor 'get_sysinfo' in response")
                if "smartplug" in type.lower():
                    devices[ip] = SmartPlug(ip)
                elif "smartbulb" in type.lower():
                    devices[ip] = SmartBulb(ip)
        except socket.timeout:
            _LOGGER.debug("Got socket timeout, which is okay.")
        except Exception as ex:
            _LOGGER.error("Got exception %s", ex, exc_info=True)
        return devices
