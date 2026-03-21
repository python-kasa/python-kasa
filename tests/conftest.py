from __future__ import annotations

import asyncio
import os
import sys
import traceback
import warnings
import weakref
from dataclasses import dataclass
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
from kasa.transports.basetransport import BaseTransport

from .device_fixtures import *  # noqa: F403
from .discovery_fixtures import *  # noqa: F403
from .fixtureinfo import fixture_info  # noqa: F401

# Parametrize tests to run with device both on and off
turn_on = pytest.mark.parametrize("turn_on", [True, False])


@dataclass
class _ClientSessionLeak:
    test_id: str
    worker_id: str
    stack: str
    gc_collected: bool = False


def _current_test_id() -> str:
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "<unknown test>")
    return current_test.rsplit(" (", maxsplit=1)[0]


def _worker_id(config: pytest.Config) -> str:
    workerinput = getattr(config, "workerinput", None)
    if workerinput is None:
        return "master"
    return workerinput.get("workerid", "master")


def _format_client_session_leaks(
    leaks: list[_ClientSessionLeak], worker_id: str | None = None
) -> str:
    if not leaks:
        return ""

    header = "Unclosed aiohttp ClientSession instances detected:\n"
    body = ""
    for index, leak in enumerate(leaks, start=1):
        body += f"\n[{index}] test: {leak.test_id}\n"
        body += f"worker: {worker_id or leak.worker_id}\n"
        body += (
            "state: garbage collected without an awaited close()\n"
            if leak.gc_collected
            else "state: still open at session finish\n"
        )
        body += "creation stack:\n"
        body += f"{leak.stack.rstrip()}\n"

    return header + body


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
    pytest.client_session_leaks = []


def pytest_testnodedown(node, error):
    worker_leaks = node.workeroutput.get("client_session_leaks", [])
    if worker_leaks:
        pytest.client_session_leaks.extend(
            _ClientSessionLeak(**leak) for leak in worker_leaks
        )
    worker_missing_methods = node.workeroutput.get("fixtures_missing_methods", {})
    for fixture, methods in worker_missing_methods.items():
        pytest.fixtures_missing_methods.setdefault(fixture, set()).update(methods)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    workerinput = getattr(config, "workerinput", None)
    if workerinput is not None:
        config.workeroutput["client_session_leaks"] = [
            {
                "test_id": leak.test_id,
                "worker_id": leak.worker_id,
                "stack": leak.stack,
                "gc_collected": leak.gc_collected,
            }
            for leak in getattr(pytest, "client_session_leaks", [])
        ]
        config.workeroutput["fixtures_missing_methods"] = {
            fixture: sorted(methods)
            for fixture, methods in getattr(
                pytest, "fixtures_missing_methods", {}
            ).items()
        }
        return

    if pytest.client_session_leaks:
        warnings.warn(
            UserWarning(_format_client_session_leaks(pytest.client_session_leaks)),
            stacklevel=1,
        )

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


@pytest.fixture(autouse=True, scope="session")
def track_client_sessions(request):  # noqa: PT004
    """Track aiohttp client sessions so CI can report where leaks came from."""
    config = request.config
    tracked_sessions: dict[int, _ClientSessionLeak] = {}
    tracked_session_finalizers: dict[int, weakref.finalize] = {}
    original_init = aiohttp.ClientSession.__init__
    original_close = aiohttp.ClientSession.close

    def _tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        session_id = id(self)
        tracked_sessions[session_id] = _ClientSessionLeak(
            test_id=_current_test_id(),
            worker_id=_worker_id(config),
            stack="".join(traceback.format_stack(limit=20)[:-1]),
        )

        def _mark_gc(_ref, sid=session_id):
            leak = tracked_sessions.get(sid)
            if leak is not None:
                leak.gc_collected = True

        tracked_session_finalizers[session_id] = weakref.finalize(self, _mark_gc, None)

    async def _tracked_close(self, *args, **kwargs):
        try:
            return await original_close(self, *args, **kwargs)
        finally:
            session_id = id(self)
            tracked_sessions.pop(session_id, None)
            finalizer = tracked_session_finalizers.pop(session_id, None)
            if finalizer is not None:
                finalizer.detach()

    aiohttp.ClientSession.__init__ = _tracked_init
    aiohttp.ClientSession.close = _tracked_close
    try:
        yield
    finally:
        aiohttp.ClientSession.__init__ = original_init
        aiohttp.ClientSession.close = original_close
        pytest.client_session_leaks = list(tracked_sessions.values())


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
