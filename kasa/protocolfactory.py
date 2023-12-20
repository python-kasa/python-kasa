"""Module for protocol factory class."""
from typing import Optional, Tuple, Type

from .aestransport import AesTransport
from .deviceconfig import DeviceConfig
from .iotprotocol import IotProtocol
from .klaptransport import KlapTransport, KlapTransportV2
from .protocol import (
    BaseTransport,
    TPLinkProtocol,
    TPLinkSmartHomeProtocol,
    _XorTransport,
)
from .smartprotocol import SmartProtocol


def get_protocol(
    config: DeviceConfig,
) -> Optional[TPLinkProtocol]:
    """Return the protocol from the connection name."""
    protocol_name = config.connection_type.device_family.value.split(".")[0]
    protocol_transport_key = (
        protocol_name + "." + config.connection_type.encryption_type.value
    )
    supported_device_protocols: dict[
        str, Tuple[Type[TPLinkProtocol], Type[BaseTransport]]
    ] = {
        "IOT.XOR": (TPLinkSmartHomeProtocol, _XorTransport),
        "IOT.KLAP": (IotProtocol, KlapTransport),
        "SMART.AES": (SmartProtocol, AesTransport),
        "SMART.KLAP": (SmartProtocol, KlapTransportV2),
    }
    if protocol_transport_key not in supported_device_protocols:
        return None

    protocol_class, transport_class = supported_device_protocols.get(
        protocol_transport_key
    )  # type: ignore
    return protocol_class(transport=transport_class(config=config))
