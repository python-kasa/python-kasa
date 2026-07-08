"""Tests for smart camera devices."""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, PropertyMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory

from kasa import Device, DeviceType, Module
from kasa.exceptions import AuthenticationError, DeviceError, KasaException
from kasa.smartcam import SmartCamDevice
from kasa.smartcam.modules.time import Time

from ..conftest import device_smartcam, hub_smartcam


@device_smartcam
async def test_state(dev: Device) -> None:
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
async def test_alias(dev: Device) -> None:
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
async def test_hub(dev: Device) -> None:
    assert dev.children
    for child in dev.children:
        assert child.modules
        assert child.device_info

        assert child.alias
        await child.update()
        assert child.device_id


@device_smartcam
async def test_wifi_scan(dev: SmartCamDevice) -> None:
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
async def test_wifi_join_success_and_errors(dev: SmartCamDevice) -> None:
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
async def test_device_time(dev: Device, freezer: FrozenDateTimeFactory) -> None:
    """Test a child device gets the time from it's parent module."""
    original_time = dev.time
    fallback_time = datetime.now(UTC).replace(tzinfo=ZoneInfo("America/New_York"))
    module = dev.modules[Module.Time]
    await module.set_time(fallback_time)
    await dev.update()
    assert dev.timezone == fallback_time.tzinfo
    # SmartCam set_time updates timezone only; device clock remains unchanged.
    assert dev.time.timestamp() == original_time.timestamp()


@device_smartcam
async def test_set_time_updates_timezone_only(
    dev: Device, caplog: pytest.LogCaptureFixture
) -> None:
    """Test SmartCam set_time updates timezone without changing clock time."""
    original_time = dev.time
    set_time_value = datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    module = dev.modules[Module.Time]

    with caplog.at_level(logging.WARNING):
        await module.set_time(set_time_value)
    await dev.update()

    assert (
        "SmartCam devices do not support setting clock time directly; only timezone settings will be updated."
        in caplog.text
    )
    assert dev.timezone == set_time_value.tzinfo
    assert dev.time.timestamp() == original_time.timestamp()


@device_smartcam
async def test_set_time_uses_current_timezone_for_naive_datetime(dev: Device) -> None:
    """Test SmartCam set_time uses the current timezone for naive datetimes."""
    module = dev.modules[Module.Time]
    set_time_value = datetime(2024, 1, 15, 12, 0)
    expected_timezone = module.timezone
    assert isinstance(expected_timezone, ZoneInfo)

    with patch.object(module, "call", AsyncMock(return_value={})) as call_mock:
        await module.set_time(set_time_value)

    call_mock.assert_awaited_once()
    call = call_mock.await_args_list[0]
    params = call.args[1]["system"]["basic"]
    assert params["timezone"] == Time._format_utc_offset(
        expected_timezone.utcoffset(set_time_value)
    )
    assert params["zone_id"] == expected_timezone.key


@pytest.mark.parametrize(
    ("set_time_value", "expected_timezone", "expected_zone_id"),
    [
        pytest.param(
            datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("UTC")),
            "UTC+00:00",
            "UTC",
            id="utc",
        ),
        pytest.param(
            datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("America/New_York")),
            "UTC-05:00",
            "America/New_York",
            id="negative-offset",
        ),
        pytest.param(
            datetime(2024, 1, 15, 12, 0, tzinfo=ZoneInfo("Asia/Kathmandu")),
            "UTC+05:45",
            "Asia/Kathmandu",
            id="partial-hour-offset",
        ),
    ],
)
@device_smartcam
async def test_set_time_formats_timezone_params(
    dev: Device,
    set_time_value: datetime,
    expected_timezone: str,
    expected_zone_id: str,
) -> None:
    """Test SmartCam set_time sends both offset and zone id."""
    module = dev.modules[Module.Time]
    with patch.object(module, "call", AsyncMock(return_value={})) as call_mock:
        await module.set_time(set_time_value)

    call_mock.assert_awaited_once()
    call = call_mock.await_args_list[0]
    assert call.args[0] == "setTimezone"
    params = call.args[1]["system"]["basic"]
    assert params["timezone"] == expected_timezone
    assert params["zone_id"] == expected_zone_id


@device_smartcam
async def test_set_time_rejects_fixed_offset_timezone(dev: Device) -> None:
    """Test SmartCam set_time rejects offsets that cannot update zone_id."""
    module = dev.modules[Module.Time]

    with pytest.raises(KasaException, match="zoneinfo timezones"):
        await module.set_time(datetime(2024, 1, 15, 12, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        pytest.param(timedelta(0), "UTC+00:00", id="utc"),
        pytest.param(timedelta(hours=-5), "UTC-05:00", id="negative"),
        pytest.param(timedelta(hours=5, minutes=45), "UTC+05:45", id="partial-hour"),
        pytest.param(None, "UTC+00:00", id="none"),
    ],
)
def test_format_utc_offset(offset: timedelta | None, expected: str) -> None:
    """Test SmartCam UTC offset formatting."""
    assert Time._format_utc_offset(offset) == expected


@device_smartcam
async def test_wifi_join_typeerror_on_non_rsa_key(dev: SmartCamDevice) -> None:
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
