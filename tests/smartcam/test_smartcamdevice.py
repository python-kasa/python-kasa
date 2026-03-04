"""Tests for smart camera devices."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta, tzinfo
from unittest.mock import AsyncMock, PropertyMock, patch
from zoneinfo import ZoneInfo

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
    original_time = dev.time
    fallback_time = datetime.now(UTC).replace(tzinfo=ZoneInfo("America/New_York"))
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.timezone == fallback_time.tzinfo
    # SmartCam set_time updates timezone only; device clock remains unchanged.
    assert dev.time.timestamp() == original_time.timestamp()


@pytest.mark.parametrize(
    ("set_time_value", "expected_timezone"),
    [
        pytest.param(datetime(2024, 1, 15, 12, 0, tzinfo=UTC), "UTC+00:00", id="utc"),
        pytest.param(
            datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York")),
            "UTC-05:00",
            id="negative-offset",
        ),
    ],
)
@device_smartcam
async def test_set_time_formats_timezone_parametrized(
    dev: Device, set_time_value: datetime, expected_timezone: str
):
    """Test SmartCam set_time formats timezone offsets consistently."""
    module = dev.modules[Module.Time]
    with patch.object(module, "call", AsyncMock(return_value={})) as call_mock:
        await module.set_time(set_time_value)

    call_mock.assert_awaited_once()
    call = call_mock.await_args_list[0]
    assert call.args[0] == "setTimezone"
    assert call.args[1]["system"]["basic"]["timezone"] == expected_timezone


@device_smartcam
async def test_set_time_format_none_offset_defaults_to_utc(dev: Device):
    """Test SmartCam set_time handles None offset as UTC+00:00."""

    class NoneOffsetTz(tzinfo):
        def utcoffset(self, dt: datetime | None) -> timedelta | None:
            return None

        def dst(self, dt: datetime | None) -> timedelta | None:
            return None

        def tzname(self, dt: datetime | None) -> str | None:
            return "NoneOffset"

    module = dev.modules[Module.Time]
    with patch.object(module, "call", AsyncMock(return_value={})) as call_mock:
        await module.set_time(datetime(2024, 1, 15, 12, 0, tzinfo=NoneOffsetTz()))

    call_mock.assert_awaited_once()
    call = call_mock.await_args_list[0]
    assert call.args[0] == "setTimezone"
    assert call.args[1]["system"]["basic"]["timezone"] == "UTC+00:00"


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
