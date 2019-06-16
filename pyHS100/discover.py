import socket
import logging
import json
from typing import Dict, Type, Optional

from pyHS100 import (
    TPLinkSmartHomeProtocol,
    SmartDevice,
    SmartPlug,
    SmartBulb,
    SmartStrip,
    SmartDeviceException,
)

_LOGGER = logging.getLogger(__name__)


class Discover:
    """Discover TPLink Smart Home devices.

    The main entry point for this library is Discover.discover(),
    which returns a dictionary of the found devices. The key is the IP address
    of the device and the value contains ready-to-use, SmartDevice-derived
    device object.

    discover_single() can be used to initialize a single device given its
    IP address. If the type of the device and its IP address is already known,
    you can initialize the corresponding device class directly without this.

    The protocol uses UDP broadcast datagrams on port 9999 for discovery.


    """

    DISCOVERY_QUERY = {
        "system": {"get_sysinfo": None},
        "emeter": {"get_realtime": None},
        "smartlife.iot.dimmer": {"get_dimmer_parameters": None},
        "smartlife.iot.common.emeter": {"get_realtime": None},
        "smartlife.iot.smartbulb.lightingservice": {"get_light_state": None},
    }

    @staticmethod
    def discover(
        protocol: TPLinkSmartHomeProtocol = None,
        port: int = 9999,
        timeout: int = 3,
        discovery_packets=3,
        return_raw=False,
    ) -> Dict[str, SmartDevice]:

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
        for i in range(discovery_packets):
            sock.sendto(encrypted_req[4:], (target, port))

        devices = {}
        _LOGGER.debug("Waiting %s seconds for responses...", timeout)

        try:
            while True:
                data, addr = sock.recvfrom(4096)
                ip, port = addr
                info = json.loads(protocol.decrypt(data))
                device_class = Discover._get_device_class(info)
                if return_raw:
                    devices[ip] = info
                elif device_class is not None:
                    devices[ip] = device_class(ip)
        except socket.timeout:
            _LOGGER.debug("Got socket timeout, which is okay.")
        except Exception as ex:
            _LOGGER.error("Got exception %s", ex, exc_info=True)
        _LOGGER.debug("Found %s devices: %s", len(devices), devices)
        return devices

    @staticmethod
    def discover_single(
        host: str, protocol: TPLinkSmartHomeProtocol = None
    ) -> Optional[SmartDevice]:
        """Discover a single device by the given IP address.

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

        return None

    @staticmethod
    def _get_device_class(info: dict) -> Optional[Type[SmartDevice]]:
        """Find SmartDevice subclass for device described by passed data."""
        if "system" in info and "get_sysinfo" in info["system"]:
            sysinfo = info["system"]["get_sysinfo"]
            if "type" in sysinfo:
                type_ = sysinfo["type"]
            elif "mic_type" in sysinfo:
                type_ = sysinfo["mic_type"]
            else:
                raise SmartDeviceException("Unable to find the device type field!")
        else:
            raise SmartDeviceException("No 'system' nor 'get_sysinfo' in response")

        if "smartplug" in type_.lower() and "children" in sysinfo:
            return SmartStrip
        elif "smartplug" in type_.lower():
            return SmartPlug
        elif "smartbulb" in type_.lower():
            return SmartBulb

        return None
