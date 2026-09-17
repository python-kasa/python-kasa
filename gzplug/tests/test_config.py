"""Config and bench profile persistence."""

from __future__ import annotations

import json

import pytest

from gzplug.config import AppConfig, BenchProfile, slugify
from kasa import DeviceConfig
from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)


def a_profile(profile_id: str = "bench-a") -> BenchProfile:
    config = DeviceConfig(
        host="192.168.10.17",
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartKasaPlug,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            https=False,
        ),
    )
    return BenchProfile(
        id=profile_id,
        label="Bench A",
        config=config.to_dict_control_credentials(exclude_credentials=True),
    )


def test_round_trip_preserves_connection_parameters(tmp_path):
    original = AppConfig(
        username="lab@example.com", password="secret", profiles=[a_profile()]
    )
    path = tmp_path / "config.json"
    original.save(path)

    loaded = AppConfig.load(path)

    assert loaded.username == "lab@example.com"
    assert loaded.profiles[0].id == "bench-a"
    rebuilt = loaded.profiles[0].device_config(loaded.credentials)
    assert rebuilt.host == "192.168.10.17"
    assert rebuilt.connection_type.encryption_type is DeviceEncryptionType.Klap
    assert rebuilt.connection_type.login_version == 2


def test_credentials_are_stored_once_not_per_profile(tmp_path):
    path = tmp_path / "config.json"
    AppConfig(
        username="lab@example.com",
        password="secret",
        profiles=[a_profile("a"), a_profile("b")],
    ).save(path)

    raw = json.loads(path.read_text())
    assert raw["credentials"]["password"] == "secret"
    for profile in raw["profiles"]:
        assert "credentials" not in profile["config"]


def test_credentials_are_injected_on_load(tmp_path):
    config = AppConfig(username="lab@example.com", password="secret")
    profile = a_profile()

    rebuilt = profile.device_config(config.credentials)

    assert rebuilt.credentials is not None
    assert rebuilt.credentials.username == "lab@example.com"


def test_missing_file_gives_usable_defaults(tmp_path):
    config = AppConfig.load(tmp_path / "nothing.json")
    assert config.profiles == []
    assert config.configured is False


def test_a_newer_config_is_refused_rather_than_misread():
    with pytest.raises(ValueError, match="newer version"):
        AppConfig.from_dict({"version": 99})


def test_upsert_replaces_rather_than_duplicates():
    config = AppConfig(profiles=[a_profile()])
    replacement = a_profile()
    replacement.label = "Bench A (moved)"

    config.upsert(replacement)

    assert len(config.profiles) == 1
    assert config.profiles[0].label == "Bench A (moved)"


def test_remove_drops_the_profile():
    config = AppConfig(profiles=[a_profile("a"), a_profile("b")])
    config.remove("a")
    assert [p.id for p in config.profiles] == ["b"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Bench 2 — plug A", "bench-2-plug-a"),
        ("  Spaces  ", "spaces"),
        ("///", "device"),
    ],
)
def test_slugify(label, expected):
    assert slugify(label) == expected
