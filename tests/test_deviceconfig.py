import json
from dataclasses import replace
from json import dumps as json_dumps
from json import loads as json_loads

import aiohttp
import pytest
from mashumaro import MissingField

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)

from .conftest import load_fixture

PLUG_XOR_CONFIG = DeviceConfig(host="127.0.0.1")
PLUG_KLAP_CONFIG = DeviceConfig(
    host="127.0.0.1",
    connection_type=DeviceConnectionParameters(
        DeviceFamily.SmartTapoPlug, DeviceEncryptionType.Klap, login_version=2
    ),
)
PLUG_NEW_KLAP_CONFIG = DeviceConfig(
    host="127.0.0.1",
    connection_type=DeviceConnectionParameters(
        DeviceFamily.IotSmartPlugSwitch,
        DeviceEncryptionType.Klap,
        login_version=2,
        new_klap=1,
    ),
)
CAMERA_AES_CONFIG = DeviceConfig(
    host="127.0.0.1",
    connection_type=DeviceConnectionParameters(
        DeviceFamily.SmartIpCamera, DeviceEncryptionType.Aes, https=True
    ),
)


async def test_serialization():
    """Test device config serialization."""
    config = DeviceConfig(host="Foo", http_client=aiohttp.ClientSession())
    config_dict = config.to_dict()
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config == config2
    assert config.to_dict_control_credentials() == config.to_dict()


@pytest.mark.parametrize(
    ("fixture_name", "expected_value"),
    [
        ("deviceconfig_plug-xor.json", PLUG_XOR_CONFIG),
        ("deviceconfig_plug-klap.json", PLUG_KLAP_CONFIG),
        ("deviceconfig_plug-new-klap.json", PLUG_NEW_KLAP_CONFIG),
        ("deviceconfig_camera-aes-https.json", CAMERA_AES_CONFIG),
    ],
    ids=lambda arg: arg.split("_")[-1] if isinstance(arg, str) else "",
)
async def test_deserialization(fixture_name: str, expected_value: DeviceConfig):
    """Test device config deserialization."""
    dict_val = json.loads(load_fixture("serialization", fixture_name))
    config = DeviceConfig.from_dict(dict_val)
    assert config == expected_value
    assert expected_value.to_dict() == dict_val


async def test_serialization_http_client():
    """Test that the http client does not try to serialize."""
    dict_val = json.loads(load_fixture("serialization", "deviceconfig_plug-klap.json"))

    config = replace(PLUG_KLAP_CONFIG, http_client=object())
    assert config.http_client

    assert config.to_dict() == dict_val


async def test_conn_param_no_https():
    """Test no https in connection param defaults to False."""
    dict_val = {
        "device_family": "SMART.TAPOPLUG",
        "encryption_type": "KLAP",
        "login_version": 2,
    }
    param = DeviceConnectionParameters.from_dict(dict_val)
    assert param.https is False
    assert param.new_klap is None
    assert param.to_dict() == {**dict_val, "https": False}


@pytest.mark.parametrize(
    ("input_value", "expected_error"),
    [
        ({"Foo": "Bar"}, MissingField),
        ("foobar", ValueError),
    ],
    ids=["invalid-dict", "not-dict"],
)
def test_deserialization_errors(input_value, expected_error):
    with pytest.raises(expected_error):
        DeviceConfig.from_dict(input_value)


async def test_credentials_hash():
    config = DeviceConfig(
        host="Foo",
        http_client=aiohttp.ClientSession(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict_control_credentials(credentials_hash="credhash")
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials_hash == "credhash"
    assert config2.credentials is None


async def test_blank_credentials_hash():
    config = DeviceConfig(
        host="Foo",
        http_client=aiohttp.ClientSession(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict_control_credentials(credentials_hash="")
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials_hash is None
    assert config2.credentials is None


async def test_exclude_credentials():
    config = DeviceConfig(
        host="Foo",
        http_client=aiohttp.ClientSession(),
        credentials=Credentials("foo", "bar"),
    )
    config_dict = config.to_dict_control_credentials(exclude_credentials=True)
    config_json = json_dumps(config_dict)
    config2_dict = json_loads(config_json)
    config2 = DeviceConfig.from_dict(config2_dict)
    assert config2.credentials is None
