from __future__ import annotations

import asyncio
import functools
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

# TODO: this and runner fixture could be moved to tests/cli/conftest.py
from asyncclick.testing import CliRunner

from kasa import (
    DeviceConfig,
    SmartProtocol,
)
from kasa.httpclient import HttpClient
from kasa.transports.basetransport import BaseTransport

from .device_fixtures import *  # noqa: F403
from .discovery_fixtures import *  # noqa: F403
from .fixtureinfo import fixture_info  # noqa: F401

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


@pytest.fixture(autouse=True)
async def _close_transport_and_http_sessions(monkeypatch):
    """Ensure all transports and http clients close their sessions after tests."""
    transports: list[BaseTransport] = []
    http_clients: list[HttpClient] = []
    aiohttp_sessions: list[aiohttp.ClientSession] = []

    original_transport_init = BaseTransport.__init__
    original_http_init = HttpClient.__init__
    original_session_init = aiohttp.ClientSession.__init__

    @functools.wraps(original_transport_init)
    def _track_transport(self, *args, **kwargs):
        original_transport_init(self, *args, **kwargs)
        transports.append(self)

    @functools.wraps(original_http_init)
    def _track_http(self, *args, **kwargs):
        original_http_init(self, *args, **kwargs)
        http_clients.append(self)

    @functools.wraps(original_session_init)
    def _track_session(self, *args, **kwargs):
        original_session_init(self, *args, **kwargs)
        aiohttp_sessions.append(self)

    monkeypatch.setattr(BaseTransport, "__init__", _track_transport)
    monkeypatch.setattr(HttpClient, "__init__", _track_http)
    monkeypatch.setattr(aiohttp.ClientSession, "__init__", _track_session)
    yield
    for transport in transports:
        await transport.close()
    for client in http_clients:
        await client.close()
    for session in aiohttp_sessions:
        if not session.closed:
            await session.close()


def load_fixture(foldername, filename):
    """Load a fixture."""
    path = Path(Path(__file__).parent / "fixtures" / foldername / filename)
    with path.open() as fdp:
        return fdp.read()


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
        # pytest_socket doesn't work properly in windows with asyncio
        # fine to disable as other platforms will pickup any issues.
        if sys.platform == "win32":
            for item in items:
                item.add_marker(pytest.mark.enable_socket)
    else:
        print("Running against ip {}".format(config.getoption("--ip")))
        requires_dummy = pytest.mark.skip(
            reason="test requires to be run against dummy data"
        )
        for item in items:
            if "requires_dummy" in item.keywords:
                item.add_marker(requires_dummy)
            else:
                item.add_marker(pytest.mark.enable_socket)


@pytest.fixture(autouse=True, scope="session")
def asyncio_sleep_fixture(request):  # noqa: PT004
    """Patch sleep to prevent tests actually waiting."""
    orig_asyncio_sleep = asyncio.sleep

    async def _asyncio_sleep(*_, **__):
        await orig_asyncio_sleep(0)

    if request.config.getoption("--ip"):
        yield
    else:
        with patch("asyncio.sleep", side_effect=_asyncio_sleep):
            yield


@pytest.fixture(autouse=True, scope="session")
def mock_datagram_endpoint(request):  # noqa: PT004
    """Mock create_datagram_endpoint so it doesn't perform io."""

    async def _create_datagram_endpoint(protocol_factory, *_, **__):
        protocol = protocol_factory()
        transport = MagicMock()
        try:
            return transport, protocol
        finally:
            protocol.connection_made(transport)

    if request.config.getoption("--ip"):
        yield
    else:
        with patch(
            "asyncio.BaseEventLoop.create_datagram_endpoint",
            side_effect=_create_datagram_endpoint,
        ):
            yield


@pytest.fixture
def runner():
    """Runner fixture that unsets the KASA_ environment variables for tests."""
    KASA_VARS = {k: None for k, v in os.environ.items() if k.startswith("KASA_")}
    runner = CliRunner(env=KASA_VARS)

    return runner
