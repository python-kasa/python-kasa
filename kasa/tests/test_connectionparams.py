from json import dumps as json_dumps
from json import loads as json_loads

import httpx

from kasa.connectionparams import (
    ConnectionParameters,
    ConnectionType,
    DeviceFamilyType,
    EncryptType,
)
from kasa.credentials import Credentials


def test_serialization():
    cp = ConnectionParameters(host="Foo", http_client=httpx.AsyncClient())
    cp_dict = cp.to_dict()
    cp_json = json_dumps(cp_dict)
    cp2_dict = json_loads(cp_json)
    cp2 = ConnectionParameters.from_dict(cp2_dict)
    assert cp == cp2
