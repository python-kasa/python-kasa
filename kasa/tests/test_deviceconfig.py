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
