import socket
import logging
import json
from typing import Dict, Type

from pyHS100 import (TPLinkSmartHomeProtocol, SmartDevice, SmartPlug,
                     SmartBulb, SmartStrip)

_LOGGER = logging.getLogger(__name__)


class Discover:
    DISCOVERY_QUERY = {"system": {"get_sysinfo": None},
                       "emeter": {"get_realtime": None}}

    @staticmethod
    def discover(protocol: TPLinkSmartHomeProtocol = None,
                 port: int = 9999,
                 timeout: int = 3) -> Dict[str, SmartDevice]:
        """
        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.

        :param protocol: Protocol implementation to use
        :param timeout: How long to wait for responses, defaults to 3
        :param port: port to send broadcast messages, defaults to 9999.
        :rtype: dict
        :return: Array of json objects {"ip", "port", "sys_info"}
        """
        if protocol is None:
            protocol = TPLinkSmartHomeProtocol()

        target = "255.255.255.255"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        req = json.dumps(Discover.DISCOVERY_QUERY)
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
                device_class = Discover._get_device_class(info)
                if device_class is not None:
                    devices[ip] = device_class(ip)
        except socket.timeout:
            _LOGGER.debug("Got socket timeout, which is okay.")
        except Exception as ex:
            _LOGGER.error("Got exception %s", ex, exc_info=True)
        return devices

    @staticmethod
    def discover_single(host: str,
                        protocol: TPLinkSmartHomeProtocol = None
                        ) -> SmartDevice:
        """
        Similar to discover(), except only return device object for a single
        host.

        :param host: Hostname of device to query
        :param protocol: Protocol implementation to use
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        if protocol is None:
            protocol = TPLinkSmartHomeProtocol()

        info = protocol.query(host, Discover.DISCOVERY_QUERY)

        device_class = Discover._get_device_class(info)
        if device_class is not None:
            return device_class(host)
        else:
            return None

    @staticmethod
    def _get_device_class(info: dict) -> Type[SmartDevice]:
        """Find SmartDevice subclass for device described by passed data."""
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

        if "smartplug" in type.lower() and "children" in sysinfo:
            return SmartStrip
        elif "smartplug" in type.lower():
            return SmartPlug
        elif "smartbulb" in type.lower():
            return SmartBulb

        return None
