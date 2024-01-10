from json import dumps as json_dumps
from json import loads as json_loads

import httpx

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    ConnectionType,
    DeviceConfig,
    DeviceFamilyType,
    EncryptType,
)


def test_serialization():
    config = DeviceConfig(host="Foo", http_client=httpx.AsyncClient())
    config_dict = config.to_dict()
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config == config2


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
