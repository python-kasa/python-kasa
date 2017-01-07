from __future__ import absolute_import
from __future__ import unicode_literals

import json
import socket
import logging

_LOGGER = logging.getLogger(__name__)


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
    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    DEFAULT_TIMEOUT = 5

    @staticmethod
    def query(host, request, port=DEFAULT_PORT):
        """
        Request information from a TP-Link SmartHome Device and return the
        response.

        :param str host: ip address of the device
        :param int port: port on the device (default: 9999)
        :param request: command to send to the device (can be either dict or
        json string)
        :return:
        """
        if isinstance(request, dict):
            request = json.dumps(request)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect((host, port))

            _LOGGER.debug("> (%i) %s", len(request), request)
            sock.send(TPLinkSmartHomeProtocol.encrypt(request))

            buffer = bytes()
            while True:
                chunk = sock.recv(4096)
                buffer += chunk
                if not chunk:
                    break

        finally:
            sock.shutdown(socket.SHUT_RDWR)
            sock.close()

        response = TPLinkSmartHomeProtocol.decrypt(buffer[4:])
        _LOGGER.debug("< (%i) %s", len(response), response)

        return json.loads(response)

    @staticmethod
    def discover(timeout=DEFAULT_TIMEOUT, port=DEFAULT_PORT):
        """
        Sends discovery message to 255.255.255.255:9999 in order
        to detect available supported devices in the local network,
        and waits for given timeout for answers from devices.

        :param timeout: How long to wait for responses, defaults to 5
        :param port: port to send broadcast messages, defaults to 9999.
        :rtype: list[dict]
        :return: Array of json objects {"ip", "port", "sys_info"}
        """
        discovery_query = {"system": {"get_sysinfo": None},
                           "emeter": {"get_realtime": None}}
        target = "255.255.255.255"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        req = json.dumps(discovery_query)
        _LOGGER.debug("Sending discovery to %s:%s", target, port)

        encrypted_req = TPLinkSmartHomeProtocol.encrypt(req)
        sock.sendto(encrypted_req[4:], (target, port))

        devices = []
        _LOGGER.debug("Waiting %s seconds for responses...", timeout)

        try:
            while True:
                data, addr = sock.recvfrom(4096)
                ip, port = addr
                info = json.loads(TPLinkSmartHomeProtocol.decrypt(data))

                devices.append({"ip": ip, "port": port, "sys_info": info})
        except Exception as ex:
            _LOGGER.error("Got exception %s", ex, exc_info=True)

        return devices

    @staticmethod
    def encrypt(request):
        """
        Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext request
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        buffer = bytearray(4)  # 4 nullbytes

        for char in request:
            cipher = key ^ ord(char)
            key = cipher
            buffer.append(cipher)

        return buffer

    @staticmethod
    def decrypt(ciphertext):
        """
        Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        buffer = []

        ciphertext = ciphertext.decode('latin-1')

        for char in ciphertext:
            plain = key ^ ord(char)
            key = ord(char)
            buffer.append(chr(plain))

        plaintext = ''.join(buffer)

        return plaintext
