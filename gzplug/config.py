"""Application settings and saved bench profiles.

Profiles are serialized with the library's own
:meth:`~kasa.DeviceConfig.to_dict_control_credentials`, not a schema of our
own, so a plug's connection parameters round-trip exactly as python-kasa
understands them. Credentials live once at the top level and are injected on
load rather than duplicated into every profile.

Credentials are stored in plaintext by deliberate choice: this is a shared lab
service account used by many testers. ``config.json`` is gitignored, but the
password is real, so that account's password must not be reused anywhere that
matters.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from kasa import Credentials, Device, DeviceConfig

_LOGGER = logging.getLogger(__name__)

CONFIG_VERSION = 1
CONFIG_FILENAME = "config.json"
RUNS_DIRNAME = "runs"

_SLUG = re.compile(r"[^a-z0-9]+")


def app_dir() -> Path:
    """Directory holding config and run logs.

    Beside the executable when frozen by PyInstaller, and the current working
    directory otherwise, which keeps a dev checkout from writing into the repo
    root by accident.
    """
    if env := os.environ.get("GZPLUG_HOME"):
        return Path(env).expanduser()
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged builds
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def config_path() -> Path:
    """Full path to ``config.json``."""
    return app_dir() / CONFIG_FILENAME


def runs_dir() -> Path:
    """Directory that per-run CSV files are written into."""
    return app_dir() / RUNS_DIRNAME


def slugify(label: str) -> str:
    """Turn a human label into a stable profile id."""
    return _SLUG.sub("-", label.strip().lower()).strip("-") or "device"


@dataclass(slots=True)
class BenchProfile:
    """A saved plug: what to call it, which plug it is, and where it was.

    The *identity* is :attr:`device_id`; the address in :attr:`config` is only
    the last place the plug was seen. A bench on DHCP hands out new leases
    after a router reboot, and a profile keyed on address silently points at
    whatever else took that address -- which surfaces as an authentication
    failure against a stranger's plug rather than as a missing device.
    """

    id: str
    label: str
    #: ``DeviceConfig`` as a dict, with credentials excluded.
    config: dict[str, Any]
    #: Stable identity, used to find this plug again if its address moves.
    device_id: str | None = None
    mac: str | None = None

    @property
    def host(self) -> str:
        """Last known address."""
        return str(self.config.get("host", "?"))

    def with_host(self, host: str) -> None:
        """Point this profile at a new address."""
        self.config = {**self.config, "host": host}

    @classmethod
    def from_device(cls, device: Device, label: str = "") -> BenchProfile:
        """Build a profile from a discovered device.

        Caching the connection parameters here is what lets normal startup
        skip the discovery round-trip, the way the scratch scripts do with
        their hardcoded values.
        """
        label = label or device.alias or device.host
        return cls(
            id=slugify(label),
            label=label,
            config=device.config.to_dict_control_credentials(exclude_credentials=True),
            device_id=device.device_id,
            mac=device.mac,
        )

    def device_config(self, credentials: Credentials | None) -> DeviceConfig:
        """Rebuild a usable :class:`~kasa.DeviceConfig` with credentials."""
        config = DeviceConfig.from_dict(dict(self.config))
        return replace(config, credentials=credentials) if credentials else config

    def to_dict(self) -> dict[str, Any]:
        """Serialize for ``config.json``."""
        return {
            "id": self.id,
            "label": self.label,
            "device_id": self.device_id,
            "mac": self.mac,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchProfile:
        """Deserialize from ``config.json``.

        ``device_id`` is optional so profiles written before identity was
        tracked still load; they are backfilled on the next good connect.
        """
        return cls(
            id=data["id"],
            label=data["label"],
            config=data["config"],
            device_id=data.get("device_id"),
            mac=data.get("mac"),
        )


@dataclass(slots=True)
class AppConfig:
    """Everything the application remembers between launches."""

    username: str = ""
    password: str = ""
    poll_interval_s: float = 2.0
    profiles: list[BenchProfile] = field(default_factory=list)

    # -- credentials ---------------------------------------------------

    @property
    def credentials(self) -> Credentials | None:
        """Shared account credentials, or None if not set up yet."""
        if not self.username or not self.password:
            return None
        return Credentials(self.username, self.password)

    @property
    def configured(self) -> bool:
        """True once credentials have been entered."""
        return self.credentials is not None

    # -- profiles ------------------------------------------------------

    def by_device_id(self, device_id: str) -> BenchProfile | None:
        """Find a profile by the plug's stable identity."""
        for profile in self.profiles:
            if profile.device_id and profile.device_id == device_id:
                return profile
        return None

    def get(self, profile_id: str) -> BenchProfile:
        """Look up one profile by id."""
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        raise KeyError(profile_id)

    def upsert(self, profile: BenchProfile) -> None:
        """Add a profile, or replace the existing one with the same id."""
        for index, existing in enumerate(self.profiles):
            if existing.id == profile.id:
                self.profiles[index] = profile
                return
        self.profiles.append(profile)

    def remove(self, profile_id: str) -> None:
        """Drop a profile, if present."""
        self.profiles = [p for p in self.profiles if p.id != profile_id]

    # -- persistence ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize for ``config.json``."""
        return {
            "version": CONFIG_VERSION,
            "credentials": {"username": self.username, "password": self.password},
            "poll_interval_s": self.poll_interval_s,
            "profiles": [p.to_dict() for p in self.profiles],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        """Deserialize from ``config.json``, tolerating missing keys."""
        version = data.get("version", CONFIG_VERSION)
        if version > CONFIG_VERSION:
            raise ValueError(
                f"config.json was written by a newer version "
                f"(v{version} > v{CONFIG_VERSION}); upgrade the application"
            )
        creds = data.get("credentials") or {}
        return cls(
            username=creds.get("username", ""),
            password=creds.get("password", ""),
            poll_interval_s=float(data.get("poll_interval_s", 2.0)),
            profiles=[BenchProfile.from_dict(p) for p in data.get("profiles", [])],
        )

    def save(self, path: Path | None = None) -> Path:
        """Write to disk atomically, so a crash cannot truncate the file."""
        target = path or config_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        temp.replace(target)
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        """Read from disk, returning defaults when there is nothing yet."""
        source = path or config_path()
        if not source.exists():
            return cls()
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))
