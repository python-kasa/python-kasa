"""Discovery module for TP-Link Smart Home devices."""
import asyncio
import json
import logging
import socket
from typing import Awaitable, Callable, Dict, Mapping, Type, Union, cast

from kasa.protocol import TPLinkSmartHomeProtocol
from kasa.smartbulb import SmartBulb
from kasa.smartdevice import SmartDevice, SmartDeviceException
from kasa.smartdimmer import SmartDimmer
from kasa.smartplug import SmartPlug
from kasa.smartstrip import SmartStrip

_LOGGER = logging.getLogger(__name__)


OnDiscoveredCallable = Callable[[SmartDevice], Awaitable[None]]


class _DiscoverProtocol(asyncio.DatagramProtocol):
    """Implementation of the discovery protocol handler.

    This is internal class, use :func:Discover.discover: instead.
    """

    discovered_devices: Dict[str, SmartDevice]
    discovered_devices_raw: Dict[str, Dict]

    def __init__(
        self,
        *,
        on_discovered: OnDiscoveredCallable = None,
        target: str = "255.255.255.255",
        timeout: int = 5,
        discovery_packets: int = 3,
    ):
        self.transport = None
        self.tries = discovery_packets
        self.timeout = timeout
        self.on_discovered = on_discovered
        self.protocol = TPLinkSmartHomeProtocol()
        self.target = (target, Discover.DISCOVERY_PORT)
        self.discovered_devices = {}
        self.discovered_devices_raw = {}

    def connection_made(self, transport) -> None:
        """Set socket options for broadcasting."""
        self.transport = transport
        sock = transport.get_extra_info("socket")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.do_discover()

    def do_discover(self) -> None:
        """Send number of discovery datagrams."""
        req = json.dumps(Discover.DISCOVERY_QUERY)
        _LOGGER.debug("[DISCOVERY] %s >> %s", self.target, Discover.DISCOVERY_QUERY)
        encrypted_req = self.protocol.encrypt(req)
        for i in range(self.tries):
            self.transport.sendto(encrypted_req[4:], self.target)  # type: ignore

    def datagram_received(self, data, addr) -> None:
        """Handle discovery responses."""
        ip, port = addr
        if ip in self.discovered_devices:
            return

        info = json.loads(self.protocol.decrypt(data))
        _LOGGER.debug("[DISCOVERY] %s << %s", ip, info)

        device_class = Discover._get_device_class(info)
        device = device_class(ip)

        self.discovered_devices[ip] = device
        self.discovered_devices_raw[ip] = info

        if device_class is not None:
            if self.on_discovered is not None:
                asyncio.ensure_future(self.on_discovered(device))
        else:
            _LOGGER.error("Received invalid response: %s", info)

    def error_received(self, ex):
        """Handle asyncio.Protocol errors."""
        _LOGGER.error("Got error: %s", ex)

    def connection_lost(self, ex):
        """NOP implementation of connection lost."""


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

    DISCOVERY_PORT = 9999

    DISCOVERY_QUERY = {
        "system": {"get_sysinfo": None},
        "emeter": {"get_realtime": None},
        "smartlife.iot.dimmer": {"get_dimmer_parameters": None},
        "smartlife.iot.common.emeter": {"get_realtime": None},
        "smartlife.iot.smartbulb.lightingservice": {"get_light_state": None},
    }

    @staticmethod
    async def discover(
        *,
        target="255.255.255.255",
        on_discovered=None,
        timeout=5,
        discovery_packets=3,
        return_raw=False,
    ) -> Mapping[str, Union[SmartDevice, Dict]]:
        """Discover supported devices.

        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.

        If given, `on_discovered` coroutine will get passed with the SmartDevice as parameter.
        The results of the discovery can be accessed either via `discovered_devices` (SmartDevice-derived) or
        `discovered_devices_raw` (JSON objects).

        :param target: The target broadcast address (e.g. 192.168.xxx.255).
        :param on_discovered:
        :param timeout: How long to wait for responses, defaults to 5
        :param discovery_packets: Number of discovery packets are broadcasted.
        :param return_raw: True to return JSON objects instead of Devices.
        :return:
        """
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoverProtocol(
                target=target,
                on_discovered=on_discovered,
                timeout=timeout,
                discovery_packets=discovery_packets,
            ),
            local_addr=("0.0.0.0", 0),
        )
        protocol = cast(_DiscoverProtocol, protocol)

        try:
            _LOGGER.debug("Waiting %s seconds for responses...", timeout)
            await asyncio.sleep(5)
        finally:
            transport.close()

        _LOGGER.debug("Discovered %s devices", len(protocol.discovered_devices))

        if return_raw:
            return protocol.discovered_devices_raw

        return protocol.discovered_devices

    @staticmethod
    async def discover_single(host: str) -> SmartDevice:
        """Discover a single device by the given IP address.

        :param host: Hostname of device to query
        :rtype: SmartDevice
        :return: Object for querying/controlling found device.
        """
        protocol = TPLinkSmartHomeProtocol()

        info = await protocol.query(host, Discover.DISCOVERY_QUERY)

        device_class = Discover._get_device_class(info)
        if device_class is not None:
            return device_class(host)

        raise SmartDeviceException("Unable to discover device, received: %s" % info)

    @staticmethod
    def _get_device_class(info: dict) -> Type[SmartDevice]:
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

        if (
            "smartlife.iot.dimmer" in info
            and "get_dimmer_parameters" in info["smartlife.iot.dimmer"]
        ):
            return SmartDimmer
        elif "smartplug" in type_.lower() and "children" in sysinfo:
            return SmartStrip
        elif "smartplug" in type_.lower():
            return SmartPlug
        elif "smartbulb" in type_.lower():
            return SmartBulb

        raise SmartDeviceException("Unknown device type: %s", type_)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()

    async def _on_device(dev):
        await dev.update()
        _LOGGER.info("Got device: %s", dev)

    devices = loop.run_until_complete(Discover.discover(on_discovered=_on_device))
    for ip, dev in devices.items():
        print(f"[{ip}] {dev}")
