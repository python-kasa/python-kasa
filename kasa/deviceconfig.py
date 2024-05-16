"""Module for holding connection parameters.

Note that this module does not work with from __future__ import annotations
due to it's use of type returned by fields() which becomes a string with the import.
https://bugs.python.org/issue39442
"""

# ruff: noqa: FA100
import logging
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum
from typing import TYPE_CHECKING, Dict, Optional, Union

from .credentials import Credentials
from .exceptions import KasaException

if TYPE_CHECKING:
    from aiohttp import ClientSession

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
    SmartTapoSwitch = "SMART.TAPOSWITCH"
    SmartTapoHub = "SMART.TAPOHUB"
    SmartKasaHub = "SMART.KASAHUB"


def _dataclass_from_dict(klass, in_val):
    if is_dataclass(klass):
        fieldtypes = {f.name: f.type for f in fields(klass)}
        val = {}
        for dict_key in in_val:
            if dict_key in fieldtypes:
                if hasattr(fieldtypes[dict_key], "from_dict"):
                    val[dict_key] = fieldtypes[dict_key].from_dict(in_val[dict_key])
                else:
                    val[dict_key] = _dataclass_from_dict(
                        fieldtypes[dict_key], in_val[dict_key]
                    )
            else:
                raise KasaException(
                    f"Cannot create dataclass from dict, unknown key: {dict_key}"
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
    login_version: Optional[int] = None

    @staticmethod
    def from_values(
        device_family: str,
        encryption_type: str,
        login_version: Optional[int] = None,
    ) -> "ConnectionType":
        """Return connection parameters from string values."""
        try:
            return ConnectionType(
                DeviceFamilyType(device_family),
                EncryptType(encryption_type),
                login_version,
            )
        except (ValueError, TypeError) as ex:
            raise KasaException(
                f"Invalid connection parameters for {device_family}."
                + f"{encryption_type}.{login_version}"
            ) from ex

    @staticmethod
    def from_dict(connection_type_dict: Dict[str, str]) -> "ConnectionType":
        """Return connection parameters from dict."""
        if (
            isinstance(connection_type_dict, dict)
            and (device_family := connection_type_dict.get("device_family"))
            and (encryption_type := connection_type_dict.get("encryption_type"))
        ):
            if login_version := connection_type_dict.get("login_version"):
                login_version = int(login_version)  # type: ignore[assignment]
            return ConnectionType.from_values(
                device_family,
                encryption_type,
                login_version,  # type: ignore[arg-type]
            )

        raise KasaException(f"Invalid connection type data for {connection_type_dict}")

    def to_dict(self) -> Dict[str, Union[str, int]]:
        """Convert connection params to dict."""
        result: Dict[str, Union[str, int]] = {
            "device_family": self.device_family.value,
            "encryption_type": self.encryption_type.value,
        }
        if self.login_version:
            result["login_version"] = self.login_version
        return result


@dataclass
class DeviceConfig:
    """Class to represent paramaters that determine how to connect to devices."""

    DEFAULT_TIMEOUT = 5
    #: IP address or hostname
    host: str
    #: Timeout for querying the device
    timeout: Optional[int] = DEFAULT_TIMEOUT
    #: Override the default 9999 port to support port forwarding
    port_override: Optional[int] = None
    #: Credentials for devices requiring authentication
    credentials: Optional[Credentials] = None
    #: Credentials hash for devices requiring authentication.
    #: If credentials are also supplied they take precendence over credentials_hash.
    #: Credentials hash can be retrieved from :attr:`Device.credentials_hash`
    credentials_hash: Optional[str] = None
    #: The protocol specific type of connection.  Defaults to the legacy type.
    batch_size: Optional[int] = None
    #: The batch size for protoools supporting multiple request batches.
    connection_type: ConnectionType = field(
        default_factory=lambda: ConnectionType(
            DeviceFamilyType.IotSmartPlugSwitch, EncryptType.Xor, 1
        )
    )
    #: True if the device uses http.  Consumers should retrieve rather than set this
    #: in order to determine whether they should pass a custom http client if desired.
    uses_http: bool = False

    # compare=False will be excluded from the serialization and object comparison.
    #: Set a custom http_client for the device to use.
    http_client: Optional["ClientSession"] = field(default=None, compare=False)

    def __post_init__(self):
        if self.connection_type is None:
            self.connection_type = ConnectionType(
                DeviceFamilyType.IotSmartPlugSwitch, EncryptType.Xor
            )

    def to_dict(
        self,
        *,
        credentials_hash: Optional[str] = None,
        exclude_credentials: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        """Convert device config to dict."""
        if credentials_hash is not None or exclude_credentials:
            self.credentials = None
        if credentials_hash:
            self.credentials_hash = credentials_hash
        return _dataclass_to_dict(self)

    @staticmethod
    def from_dict(config_dict: Dict[str, Dict[str, str]]) -> "DeviceConfig":
        """Return device config from dict."""
        if isinstance(config_dict, dict):
            return _dataclass_from_dict(DeviceConfig, config_dict)
        raise KasaException(f"Invalid device config data: {config_dict}")
