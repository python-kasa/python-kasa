"""API tests, driven in-process over ASGI so no socket is opened."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from gzplug.api.app import create_app
from kasa import DeviceConfig
from kasa.deviceconfig import (
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)

from .conftest import FakeDevice, FakeEnergy

HOST_A = "192.168.0.11"
HOST_B = "192.168.0.12"


def device_config(host: str) -> dict:
    config = DeviceConfig(
        host=host,
        connection_type=DeviceConnectionParameters(
            device_family=DeviceFamily.SmartKasaPlug,
            encryption_type=DeviceEncryptionType.Klap,
            login_version=2,
            https=False,
        ),
    )
    return config.to_dict_control_credentials(exclude_credentials=True)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point config.json and runs/ at a temp directory."""
    monkeypatch.setenv("GZPLUG_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def plugs():
    """Return two well-behaved fakes, one on and one off."""
    return {
        HOST_A: FakeDevice(is_on=False, alias="Bench A", energy=FakeEnergy()),
        HOST_B: FakeDevice(is_on=True, alias="Bench B", energy=FakeEnergy()),
    }


def write_config(home, *, credentials=True, hosts=(HOST_A, HOST_B)) -> None:
    payload = {
        "version": 1,
        "credentials": (
            {"username": "lab@example.com", "password": "pw"}
            if credentials
            else {"username": "", "password": ""}
        ),
        "poll_interval_s": 0.05,
        "profiles": [
            {
                "id": f"bench-{index}",
                "label": f"Bench {index}",
                "config": device_config(host),
            }
            for index, host in enumerate(hosts, start=1)
        ],
    }
    (home / "config.json").write_text(json.dumps(payload))


@pytest.fixture
def client(home, plugs, monkeypatch):
    """Return a running app wired to the fake plugs."""
    write_config(home)

    async def fake_connect(*, config):
        try:
            return plugs[config.host]
        except KeyError:
            raise OSError(f"no fake plug at {config.host}") from None

    monkeypatch.setattr(
        "gzplug.core.session.Device.connect", staticmethod(fake_connect)
    )
    with TestClient(create_app()) as test_client:
        yield test_client


def wait_for_run(client: TestClient, timeout: float = 10.0) -> dict:
    """Poll until the run leaves the running state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get("/api/state").json()["run"]
        if run["state"] != "running":
            return run
        time.sleep(0.02)
    raise AssertionError("run did not finish in time")


# -- state -------------------------------------------------------------


def test_state_lists_connected_devices(client):
    body = client.get("/api/state").json()

    assert body["configured"] is True
    assert body["maxDevices"] == 4
    assert [d["id"] for d in body["devices"]] == ["bench-1", "bench-2"]
    assert all(d["connected"] for d in body["devices"])
    assert body["devices"][0]["power_w"] == 12.5
    assert body["run"]["state"] == "idle"


def test_an_offline_plug_does_not_block_the_others(home, monkeypatch):
    """A dashboard must come up with three of four benches working."""
    write_config(home, hosts=(HOST_A, "10.0.0.99"))
    good = FakeDevice(alias="Bench A", energy=FakeEnergy())

    async def fake_connect(*, config):
        if config.host == HOST_A:
            return good
        raise OSError("host unreachable")

    monkeypatch.setattr(
        "gzplug.core.session.Device.connect", staticmethod(fake_connect)
    )

    with TestClient(create_app()) as client:
        devices = client.get("/api/state").json()["devices"]

    assert devices[0]["connected"] is True
    assert devices[1]["connected"] is False
    assert "unreachable" in devices[1]["error"]


def test_credentials_can_be_set_from_the_browser(home, monkeypatch):
    write_config(home, credentials=False)
    monkeypatch.setattr(
        "gzplug.core.session.Device.connect",
        staticmethod(lambda *, config: _ok(FakeDevice())),
    )

    with TestClient(create_app()) as client:
        assert client.get("/api/state").json()["configured"] is False
        body = client.post(
            "/api/credentials",
            json={"username": "lab@example.com", "password": "pw"},
        ).json()

    assert body["configured"] is True
    assert (
        json.loads((home / "config.json").read_text())["credentials"]["username"]
        == "lab@example.com"
    )


# -- identity and relocation -------------------------------------------


def test_a_plug_that_moved_address_is_found_again(home, monkeypatch):
    """The DHCP case: the saved address is stale, the plug is elsewhere.

    Keying a bench position on its address means a router reboot silently
    breaks it -- and worse, points it at whatever else took that address, so
    it surfaces as an authentication failure rather than a missing plug.
    """
    write_config(home, hosts=(HOST_A,))
    raw = json.loads((home / "config.json").read_text())
    raw["profiles"][0]["device_id"] = "PLUG-ONE"
    (home / "config.json").write_text(json.dumps(raw))

    moved = FakeDevice(alias="Bench A", energy=FakeEnergy(), device_id="PLUG-ONE")
    new_host = "192.168.0.77"

    async def fake_connect(*, config):
        if config.host == new_host:
            return moved
        raise OSError("host unreachable")

    async def fake_discover(**kwargs):
        return {new_host: moved}

    monkeypatch.setattr(
        "gzplug.core.session.Device.connect", staticmethod(fake_connect)
    )
    monkeypatch.setattr(
        "gzplug.api.state.Discover.discover", staticmethod(fake_discover)
    )

    with TestClient(create_app()) as client:
        device = client.get("/api/state").json()["devices"][0]

    assert device["connected"] is True, "the plug should have been found again"
    assert device["host"] == new_host
    assert device["relocated_from"] == HOST_A

    saved = json.loads((home / "config.json").read_text())["profiles"][0]
    assert saved["config"]["host"] == new_host, "the new address must be saved"


def test_identity_is_backfilled_for_profiles_saved_before_it_was_tracked(
    home, monkeypatch
):
    """Old config.json files have no device_id; learn it on first connect."""
    write_config(home, hosts=(HOST_A,))
    assert (
        "device_id" not in json.loads((home / "config.json").read_text())["profiles"][0]
    )

    plug = FakeDevice(alias="Bench A", energy=FakeEnergy(), device_id="PLUG-ONE")
    monkeypatch.setattr(
        "gzplug.core.session.Device.connect",
        staticmethod(lambda *, config: _ok(plug)),
    )

    with TestClient(create_app()):
        pass

    saved = json.loads((home / "config.json").read_text())["profiles"][0]
    assert saved["device_id"] == "PLUG-ONE"


def test_a_missing_plug_is_not_confused_with_a_different_one(home, monkeypatch):
    """Discovery finding *a* plug is not the same as finding *this* plug."""
    write_config(home, hosts=(HOST_A,))
    raw = json.loads((home / "config.json").read_text())
    raw["profiles"][0]["device_id"] = "PLUG-ONE"
    (home / "config.json").write_text(json.dumps(raw))

    stranger = FakeDevice(alias="Someone else", device_id="PLUG-TWO")

    async def fake_connect(*, config):
        raise OSError("host unreachable")

    async def fake_discover(**kwargs):
        return {"192.168.0.99": stranger}

    monkeypatch.setattr(
        "gzplug.core.session.Device.connect", staticmethod(fake_connect)
    )
    monkeypatch.setattr(
        "gzplug.api.state.Discover.discover", staticmethod(fake_discover)
    )

    with TestClient(create_app()) as client:
        device = client.get("/api/state").json()["devices"][0]

    assert device["connected"] is False
    assert device["host"] == HOST_A, "must not adopt an unrelated plug's address"


# -- richer readings ---------------------------------------------------


def test_state_exposes_the_surveyed_fields(client):
    device = client.get("/api/state").json()["devices"][0]

    assert device["energy_month_kwh"] == 0.971
    assert device["overheated"] is False
    assert device["overloaded"] is False
    assert device["rssi_dbm"] == -50
    assert device["on_since"] is not None

    info = device["info"]
    assert info["firmware"] == "1.2.3 Build 240624"
    assert info["auto_update_enabled"] is True
    assert info["auto_off_enabled"] is False
    assert info["mac"] == "78:8C:B5:00:00:01"


def test_the_new_columns_reach_the_run_record(client, home):
    client.post(
        "/api/run",
        json={
            "devices": ["bench-1"],
            "cycles": 1,
            "on_time_s": 0,
            "off_time_s": 0,
            "label": "columns",
        },
    )
    wait_for_run(client)

    csv_path = next((home / "runs").glob("*.csv"))
    header, *rows = csv_path.read_text().splitlines()
    for column in ("energy_month_kwh", "overheated", "overloaded", "rssi_dbm"):
        assert column in header
    assert any("0.971" in row for row in rows)


# -- manual control ----------------------------------------------------


def test_switching_a_plug_by_hand(client, plugs):
    body = client.post("/api/devices/bench-1/switch", json={"on": True}).json()

    assert plugs[HOST_A].is_on is True
    assert body["devices"][0]["is_on"] is True


def test_switching_an_unknown_plug_is_404(client):
    assert client.post("/api/devices/nope/switch", json={"on": True}).status_code == 404


def test_removing_a_plug_forgets_it(client):
    body = client.delete("/api/devices/bench-1").json()
    assert [d["id"] for d in body["devices"]] == ["bench-2"]


# -- runs --------------------------------------------------------------


def test_run_cycles_the_plugs_and_writes_a_csv(client, plugs, home):
    started = client.post(
        "/api/run",
        json={
            "devices": ["bench-1", "bench-2"],
            "cycles": 2,
            "on_time_s": 0,
            "off_time_s": 0,
            "label": "api test",
        },
    )
    assert started.status_code == 200
    csv_name = started.json()["csv"]

    run = wait_for_run(client)
    assert run["state"] == "completed"

    csv_path = home / "runs" / csv_name
    assert csv_path.is_file()
    rows = csv_path.read_text().splitlines()
    assert rows[0].startswith("timestamp_iso,")
    assert any("turn_on" in row for row in rows)

    # Both plugs were found in opposite states and must be put back.
    assert plugs[HOST_A].is_on is False
    assert plugs[HOST_B].is_on is True


def test_a_second_run_is_refused_while_one_is_active(client):
    payload = {
        "devices": ["bench-1"],
        "cycles": 50,
        "on_time_s": 5,
        "off_time_s": 5,
    }
    assert client.post("/api/run", json=payload).status_code == 200
    try:
        assert client.post("/api/run", json=payload).status_code == 409
    finally:
        client.post("/api/run/stop")


def test_switching_by_hand_is_refused_mid_run(client):
    client.post(
        "/api/run",
        json={
            "devices": ["bench-1"],
            "cycles": 50,
            "on_time_s": 5,
            "off_time_s": 5,
        },
    )
    try:
        response = client.post("/api/devices/bench-1/switch", json={"on": True})
        assert response.status_code == 409
    finally:
        client.post("/api/run/stop")


def test_stopping_a_run_restores_the_plugs(client, plugs):
    client.post(
        "/api/run",
        json={
            "devices": ["bench-2"],
            "cycles": 50,
            "on_time_s": 5,
            "off_time_s": 5,
        },
    )
    body = client.post("/api/run/stop").json()

    assert body["run"]["state"] == "aborted"
    assert plugs[HOST_B].is_on is True, "an aborted run must still restore"


def test_run_rejects_an_unknown_device(client):
    response = client.post(
        "/api/run",
        json={"devices": ["ghost"], "cycles": 1, "on_time_s": 0, "off_time_s": 0},
    )
    assert response.status_code in (404, 409)


@pytest.mark.parametrize(
    "payload",
    [
        {"devices": [], "cycles": 1, "on_time_s": 0, "off_time_s": 0},
        {"devices": ["bench-1"], "cycles": 0, "on_time_s": 0, "off_time_s": 0},
        {"devices": ["bench-1"], "cycles": 1, "on_time_s": -1, "off_time_s": 0},
    ],
)
def test_bad_run_parameters_are_rejected(client, payload):
    assert client.post("/api/run", json=payload).status_code == 422


# -- run records -------------------------------------------------------


def test_run_records_can_be_listed_and_downloaded(client, home):
    client.post(
        "/api/run",
        json={
            "devices": ["bench-1"],
            "cycles": 1,
            "on_time_s": 0,
            "off_time_s": 0,
            "label": "download me",
        },
    )
    wait_for_run(client)

    listing = client.get("/api/runs").json()
    assert len(listing) == 1

    download = client.get(f"/api/runs/{listing[0]['name']}")
    assert download.status_code == 200
    assert download.text.startswith("timestamp_iso,")


@pytest.mark.parametrize("name", ["../config.json", "..%2Fconfig.json", "nope.csv"])
def test_run_download_will_not_escape_the_runs_directory(client, name):
    assert client.get(f"/api/runs/{name}").status_code == 404


# -- websocket ---------------------------------------------------------


def test_websocket_opens_with_a_full_snapshot(client):
    with client.websocket_connect("/ws") as socket:
        message = socket.receive_json()

    assert message["type"] == "snapshot"
    assert [d["id"] for d in message["data"]["devices"]] == ["bench-1", "bench-2"]


def test_websocket_streams_events_with_state_attached(client):
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "snapshot"
        client.post("/api/devices/bench-1/switch", json={"on": True})

        for _ in range(20):
            message = socket.receive_json()
            if message["type"] == "event" and message["data"]["kind"] == "command":
                assert message["data"]["action"] == "turn_on"
                assert message["state"]["devices"][0]["is_on"] is True
                return

    raise AssertionError("no command event arrived on the socket")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "192.168.12.65: connect failed: ('Device connection error: Cannot "
            "connect to host 192.168.12.65:80 ssl:<ssl.SSLContext object at "
            "0x10b7ea990> [Host is down]', ClientConnectorError(...), "
            "OSError(64, 'Host is down'))",
            "Host is down - the plug is not answering at this address.",
        ),
        (
            "Device response did not match our challenge on ip 192.168.10.17",
            "Authentication failed - check the account credentials, "
            "or re-pair this plug.",
        ),
        ("something short", "something short"),
    ],
)
def test_connection_errors_are_reduced_to_one_line(raw, expected):
    """A raw aiohttp error is hundreds of characters and unreadable on a card."""
    from gzplug.api.state import summarize_error

    short, full = summarize_error(OSError(raw))
    assert short == expected
    assert full == raw, "the original must still be available behind a disclosure"


def test_a_very_long_unrecognised_error_is_truncated():
    from gzplug.api.state import summarize_error

    short, full = summarize_error(OSError("x" * 500))
    assert len(short) < 200
    assert short.endswith("...")
    assert len(full) == 500


def test_a_websocket_library_is_installed():
    """Guard the trap that the ASGI tests cannot see.

    Starlette's TestClient speaks ASGI directly, so every websocket test above
    passes whether or not uvicorn can actually perform an HTTP upgrade. A real
    uvicorn without a websocket library answers /ws with 404 and the page
    silently never updates. Caught against a live server, 2026-09-17.
    """
    import importlib.util

    assert (
        importlib.util.find_spec("websockets") is not None
        or importlib.util.find_spec("wsproto") is not None
    ), "install gzplug/requirements.txt -- uvicorn needs a websocket library"


async def _ok(device):
    return device
