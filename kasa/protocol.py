"""Implementation of the TP-Link Smart Home Protocol.

Encryption/Decryption methods based on the works of
Lubomir Stroetmann and Tobias Esser

https://www.softscheck.com/en/reverse-engineering-tp-link-hs110/
https://github.com/softScheck/tplink-smartplug/

which are licensed under the Apache License, Version 2.0
http://www.apache.org/licenses/LICENSE-2.0
"""
import asyncio
import json
import logging
import struct
from pprint import pformat as pf
from typing import Dict, Union

from .exceptions import SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class TPLinkSmartHomeProtocol:
    """Implementation of the TP-Link Smart Home protocol."""

    INITIALIZATION_VECTOR = 171
    DEFAULT_PORT = 9999
    DEFAULT_TIMEOUT = 5

    @staticmethod
    async def query(host: str, request: Union[str, Dict], retry_count: int = 3) -> Dict:
        """Request information from a TP-Link SmartHome Device.

        :param str host: host name or ip address of the device
        :param request: command to send to the device (can be either dict or
        json string)
        :param retry_count: how many retries to do in case of failure
        :return: response dict
        """
        if isinstance(request, dict):
            request = json.dumps(request)

        timeout = TPLinkSmartHomeProtocol.DEFAULT_TIMEOUT
        writer = None
        for retry in range(retry_count + 1):
            try:
                task = asyncio.open_connection(
                    host, TPLinkSmartHomeProtocol.DEFAULT_PORT
                )
                reader, writer = await asyncio.wait_for(task, timeout=timeout)
                _LOGGER.debug("> (%i) %s", len(request), request)
                writer.write(TPLinkSmartHomeProtocol.encrypt(request))
                await writer.drain()

                buffer = bytes()
                # Some devices send responses with a length header of 0 and
                # terminate with a zero size chunk. Others send the length and
                # will hang if we attempt to read more data.
                length = -1
                while True:
                    chunk = await reader.read(4096)
                    if length == -1:
                        length = struct.unpack(">I", chunk[0:4])[0]
                    buffer += chunk
                    if (length > 0 and len(buffer) >= length + 4) or not chunk:
                        break

                response = TPLinkSmartHomeProtocol.decrypt(buffer[4:])
                json_payload = json.loads(response)
                _LOGGER.debug("< (%i) %s", len(response), pf(json_payload))

                return json_payload

            except Exception as ex:
                if retry >= retry_count:
                    _LOGGER.debug("Giving up after %s retries", retry)
                    raise SmartDeviceException(
                        "Unable to query the device: %s" % ex
                    ) from ex

                _LOGGER.debug("Unable to query the device, retrying: %s", ex)

            finally:
                if writer:
                    writer.close()
                    await writer.wait_closed()

        # make mypy happy, this should never be reached..
        raise SmartDeviceException("Query reached somehow to unreachable")

    @staticmethod
    def encrypt(request: str) -> bytes:
        """Encrypt a request for a TP-Link Smart Home Device.

        :param request: plaintext request data
        :return: ciphertext to be send over wire, in bytes
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR

        plainbytes = request.encode()
        buffer = bytearray(struct.pack(">I", len(plainbytes)))

        for plainbyte in plainbytes:
            cipherbyte = key ^ plainbyte
            key = cipherbyte
            buffer.append(cipherbyte)

        return bytes(buffer)

    @staticmethod
    def decrypt(ciphertext: bytes) -> str:
        """Decrypt a response of a TP-Link Smart Home Device.

        :param ciphertext: encrypted response data
        :return: plaintext response
        """
        key = TPLinkSmartHomeProtocol.INITIALIZATION_VECTOR
        buffer = []

        for cipherbyte in ciphertext:
            plainbyte = key ^ cipherbyte
            key = cipherbyte
            buffer.append(plainbyte)

        plaintext = bytes(buffer)

        return plaintext.decode()
