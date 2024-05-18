from __future__ import annotations

import warnings
from unittest.mock import MagicMock, patch

import pytest

from kasa import (
    DeviceConfig,
    SmartProtocol,
)
from kasa.protocol import BaseTransport

from .device_fixtures import *  # noqa: F403
from .discovery_fixtures import *  # noqa: F403

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


async def handle_turn_on(dev, turn_on):
    if turn_on:
        await dev.turn_on()
    else:
        await dev.turn_off()


@pytest.fixture
def dummy_protocol():
    """Return a smart protocol instance with a mocking-ready dummy transport."""

    class DummyTransport(BaseTransport):
        @property
        def default_port(self) -> int:
            return -1

        @property
        def credentials_hash(self) -> str:
            return "dummy hash"

        async def send(self, request: str) -> dict:
            return {}

        async def close(self) -> None:
            pass

        async def reset(self) -> None:
            pass

    transport = DummyTransport(config=DeviceConfig(host="127.0.0.123"))
    protocol = SmartProtocol(transport=transport)
    with patch.object(protocol, "BACKOFF_SECONDS_AFTER_TIMEOUT", 0):
        yield protocol


def pytest_configure():
    pytest.fixtures_missing_methods = {}


def pytest_sessionfinish(session, exitstatus):
    if not pytest.fixtures_missing_methods:
        return
    msg = "\n"
    for fixture, methods in sorted(pytest.fixtures_missing_methods.items()):
        method_list = ", ".join(methods)
        msg += f"Fixture {fixture} missing: {method_list}\n"

    warnings.warn(
        UserWarning(msg),
        stacklevel=1,
    )


def pytest_addoption(parser):
    parser.addoption(
        "--ip", action="store", default=None, help="run against device on given ip"
    )
    parser.addoption(
        "--username", action="store", default=None, help="authentication username"
    )
    parser.addoption(
        "--password", action="store", default=None, help="authentication password"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--ip"):
        print("Testing against fixtures.")
    else:
        print("Running against ip %s" % config.getoption("--ip"))
        requires_dummy = pytest.mark.skip(
            reason="test requires to be run against dummy data"
        )
        for item in items:
            if "requires_dummy" in item.keywords:
                item.add_marker(requires_dummy)


# allow mocks to be awaited
# https://stackoverflow.com/questions/51394411/python-object-magicmock-cant-be-used-in-await-expression/51399767#51399767


async def async_magic():
    pass


MagicMock.__await__ = lambda x: async_magic().__await__()
