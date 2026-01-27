"""Tests for smart camera devices."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Device, DeviceType, Module
from kasa.exceptions import AuthenticationError, DeviceError, KasaException
from kasa.smartcam import SmartCamDevice

from ..conftest import device_smartcam, hub_smartcam


@device_smartcam
async def test_state(dev: Device):
    if dev.device_type is DeviceType.Hub:
        pytest.skip("Hubs cannot be switched on and off")

    if Module.LensMask in dev.modules:
        state = dev.is_on
        await dev.set_state(not state)
        await dev.update()
        assert dev.is_on is not state

        dev.modules.pop(Module.LensMask)  # type: ignore[attr-defined]

    # Test with no lens mask module. Device is always on.
    assert dev.is_on is True
    res = await dev.set_state(False)
    assert res == {}
    await dev.update()
    assert dev.is_on is True


@device_smartcam
async def test_alias(dev: Device):
    test_alias = "TEST1234"
    original = dev.alias

    assert isinstance(original, str)
    await dev.set_alias(test_alias)
    await dev.update()
    assert dev.alias == test_alias

    await dev.set_alias(original)
    await dev.update()
    assert dev.alias == original


@hub_smartcam
async def test_hub(dev: Device):
    assert dev.children
    for child in dev.children:
        assert child.modules
        assert child.device_info

        assert child.alias
        await child.update()
        assert child.device_id


@device_smartcam
async def test_wifi_scan(dev: SmartCamDevice):
    fake_scan_data = {
        "scanApList": {
            "onboarding": {
                "scan": {
                    "publicKey": base64.b64encode(b"fakekey").decode(),
                    "ap_list": [
                        {
                            "ssid": "TestSSID",
                            "auth": "WPA2",
                            "encryption": "AES",
                            "channel": 6,
                            "rssi": -40,
                            "bssid": "00:11:22:33:44:55",
                        }
                    ],
                }
            }
        }
    }
    with patch.object(dev, "_query_helper", AsyncMock(return_value=fake_scan_data)):
        networks = await dev.wifi_scan()
        assert len(networks) == 1
        net = networks[0]
        assert net.ssid == "TestSSID"
        assert net.auth == "WPA2"
        assert net.encryption == "AES"
        assert net.channel == 6
        assert net.rssi == -40
        assert net.bssid == "00:11:22:33:44:55"
        assert dev._public_key == base64.b64encode(b"fakekey").decode()


@device_smartcam
async def test_wifi_join_success_and_errors(dev: SmartCamDevice):
    dev._networks = [
        type(
            "WifiNetwork",
            (),
            {
                "ssid": "TestSSID",
                "auth": "WPA2",
                "encryption": "AES",
                "channel": 6,
                "rssi": -40,
                "bssid": "00:11:22:33:44:55",
            },
        )()
    ]
    with patch.object(type(dev), "credentials", new_callable=PropertyMock) as cred_mock:
        cred_mock.return_value = object()
        with patch.object(dev.protocol, "query", AsyncMock(return_value={})):
            result = await dev.wifi_join("TestSSID", "password123")
            assert isinstance(result, dict)
        cred_mock.return_value = None
        with pytest.raises(AuthenticationError):
            await dev.wifi_join("TestSSID", "password123")
        cred_mock.return_value = object()
        dev._networks = []
        with (
            patch.object(dev, "wifi_scan", AsyncMock(return_value=[])),
            pytest.raises(DeviceError),
        ):
            await dev.wifi_join("TestSSID", "password123")
        dev._networks = [
            type(
                "WifiNetwork",
                (),
                {
                    "ssid": "TestSSID",
                    "auth": "WPA2",
                    "encryption": "AES",
                    "channel": 6,
                    "rssi": -40,
                    "bssid": "00:11:22:33:44:55",
                },
            )()
        ]
        with (
            patch.object(
                dev.protocol, "query", AsyncMock(side_effect=DeviceError("fail"))
            ),
            pytest.raises(DeviceError),
        ):
            await dev.wifi_join("TestSSID", "password123")
        with patch.object(
            dev.protocol, "query", AsyncMock(side_effect=KasaException("fail"))
        ):
            result = await dev.wifi_join("TestSSID", "password123")
            assert result == {}


@device_smartcam
async def test_device_time(dev: Device, freezer: FrozenDateTimeFactory):
    """Test a child device gets the time from it's parent module."""
    fallback_time = datetime.now(UTC).astimezone().replace(microsecond=0)
    assert dev.time != fallback_time
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.time == fallback_time


@device_smartcam
async def test_wifi_join_typeerror_on_non_rsa_key(dev: SmartCamDevice):
    dev._networks = [
        type(
            "WifiNetwork",
            (),
            {
                "ssid": "TestSSID",
                "auth": "WPA2",
                "encryption": "AES",
                "channel": 6,
                "rssi": -40,
                "bssid": "00:11:22:33:44:55",
            },
        )()
    ]
    with patch.object(type(dev), "credentials", new_callable=PropertyMock) as cred_mock:
        cred_mock.return_value = object()
        with (
            patch(
                "cryptography.hazmat.primitives.serialization.load_der_public_key",
                return_value=object(),
            ),
            patch(
                "kasa.smartcam.smartcamdevice.RSAPublicKey",
                new=type("FakeRSA", (), {}),
            ),
            pytest.raises(
                TypeError, match="Loaded public key is not an RSA public key"
            ),
        ):
            await dev.wifi_join("TestSSID", "password123")
