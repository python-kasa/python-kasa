"""Module for holding connection parameters."""
import logging
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Dict, Optional

import httpx

from .credentials import Credentials
from .exceptions import SmartDeviceException

_LOGGER = logging.getLogger(__name__)


class EncryptType(Enum):
    """Encrypt type enum."""

    Klap = "KLAP"
    Aes = "AES"
    Xor = "XOR"


class DeviceFamilyType(Enum):
    """Encrypt type enum."""

    IotSmartPlugSwitch = "IOT.SMARTPLUGSWITCH"
    IotSmartBulb = "IOT.SMARTBULB"
    SmartKasaPlug = "SMART.KASAPLUG"
    SmartKasaSwitch = "SMART.KASASWITCH"
    SmartTapoPlug = "SMART.TAPOPLUG"
    SmartTapoBulb = "SMART.TAPOBULB"


def _dataclass_from_dict(klass, in_val):
    if is_dataclass(klass):
        fieldtypes = {f.name: f.type for f in fields(klass)}
        val = {}
        for dict_key in in_val:
            if dict_key in fieldtypes and hasattr(fieldtypes[dict_key], "from_dict"):
                val[dict_key] = fieldtypes[dict_key].from_dict(in_val[dict_key])
            else:
                val[dict_key] = _dataclass_from_dict(
                    fieldtypes[dict_key], in_val[dict_key]
                )
        return klass(**val)
    else:
        return in_val


def _dataclass_to_dict(in_val):
    fieldtypes = {f.name: f.type for f in fields(in_val) if f.compare}
    out_val = {}
    for field_name in fieldtypes:
        val = getattr(in_val, field_name)
        if val is None:
            continue
        elif hasattr(val, "to_dict"):
            out_val[field_name] = val.to_dict()
        elif is_dataclass(fieldtypes[field_name]):
            out_val[field_name] = asdict(val)
        else:
            out_val[field_name] = val
    return out_val


@dataclass
class ConnectionType:
    """Class to hold the the parameters determining connection type."""

    device_family: DeviceFamilyType
    encryption_type: EncryptType

    @staticmethod
    def from_values(
        device_family: str,
        encryption_type: str,
    ) -> "ConnectionType":
        """Return connection parameters from string values."""
        try:
            return ConnectionType(
                DeviceFamilyType(device_family),
                EncryptType(encryption_type),
            )
        except ValueError as ex:
            raise SmartDeviceException(
                f"Invalid connection parameters for {device_family}.{encryption_type}"
            ) from ex

    @staticmethod
    def from_dict(connection_type_dict: Dict[str, str]) -> "ConnectionType":
        """Return connection parameters from dict."""
        if (
            isinstance(connection_type_dict, dict)
            and (device_family := connection_type_dict.get("device_family"))
            and (encryption_type := connection_type_dict.get("encryption_type"))
        ):
            return ConnectionType.from_values(device_family, encryption_type)

        raise SmartDeviceException(
            f"Invalid connection type data for {connection_type_dict}"
        )

    def to_dict(self) -> Dict[str, str]:
        """Convert connection params to dict."""
        result = {
            "device_family": self.device_family.value,
            "encryption_type": self.encryption_type.value,
        }
        return result


@dataclass
class DeviceConfig:
    """Class to represent paramaters that determine how to connect to devices."""

    DEFAULT_TIMEOUT = 5

    host: str
    timeout: Optional[int] = DEFAULT_TIMEOUT
    port_override: Optional[int] = None
    credentials: Credentials = field(
        default_factory=lambda: Credentials(username="", password="")
    )
    connection_type: ConnectionType = field(
        default_factory=lambda: ConnectionType(
            DeviceFamilyType.IotSmartPlugSwitch, EncryptType.Xor
        )
    )

    uses_http: bool = False
    # compare=False will be excluded from the serialization and object comparison.
    http_client: Optional[httpx.AsyncClient] = field(default=None, compare=False)

    def __post_init__(self):
        if self.credentials is None:
            self.credentials = Credentials(username="", password="")
        if self.connection_type is None:
            self.connection_type = ConnectionType(
                DeviceFamilyType.IotSmartPlugSwitch, EncryptType.Xor
            )

    def to_dict(self) -> Dict[str, Dict[str, str]]:
        """Convert connection params to dict."""
        return _dataclass_to_dict(self)

    @staticmethod
    def from_dict(cparam_dict: Dict[str, Dict[str, str]]) -> "DeviceConfig":
        """Return connection parameters from dict."""
        return _dataclass_from_dict(DeviceConfig, cparam_dict)
