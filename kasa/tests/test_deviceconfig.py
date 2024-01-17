from json import dumps as json_dumps
from json import loads as json_loads

import httpx
import pytest

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
    DeviceFamilyType,
    EncryptType,
)
from kasa.exceptions import SmartDeviceException


def test_serialization():
    config = DeviceConfig(host="Foo", http_client=httpx.AsyncClient())
    config_dict = config.to_dict()
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config == config2


@pytest.mark.parametrize(
    ("input_value", "expected_msg"),
    [
        ({"Foo": "Bar"}, "Cannot create dataclass from dict, unknown key: Foo"),
        ("foobar", "Invalid device config data: foobar"),
    ],
    ids=["invalid-dict", "not-dict"],
)
def test_deserialization_errors(input_value, expected_msg):
    with pytest.raises(SmartDeviceException, match=expected_msg):
        DeviceConfig.from_dict(input_value)


def test_credentials_hash():
    config = DeviceConfig(
        host="Foo",
        http_client=httpx.AsyncClient(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict(credentials_hash="credhash")
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials_hash == "credhash"
    assert config2.credentials is None


def test_blank_credentials_hash():
    config = DeviceConfig(
        host="Foo",
        http_client=httpx.AsyncClient(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict(credentials_hash="")
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials_hash is None
    assert config2.credentials is None


def test_exclude_credentials():
    config = DeviceConfig(
        host="Foo",
        http_client=httpx.AsyncClient(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict(exclude_credentials=True)
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials is None
