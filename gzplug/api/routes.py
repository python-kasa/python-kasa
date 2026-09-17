"""REST endpoints.

Every handler is a thin translation from HTTP to a call on
:class:`~gzplug.api.state.AppState`. Device logic stays in :mod:`gzplug.core`,
so the browser and the CLI drive exactly the same code.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from kasa import Discover, KasaException, UnsupportedDeviceError

from ..config import BenchProfile, runs_dir
from ..core.registry import MAX_DEVICES, RegistryError
from ..core.runner import RunPlan
from ..core.session import SessionFault
from .schemas import AddDeviceIn, CredentialsIn, DiscoverIn, RunIn, SwitchIn
from .state import AppState

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

#: Shown whenever a plug turns out to be on TPAP firmware. The operator can
#: fix this themselves in under a minute, so the API says how rather than
#: just reporting that the device is unsupported.
TPAP_HELP = (
    "This plug uses TPAP encryption, which python-kasa does not support yet. "
    "In the Tapo app: Profile > Third Party Services > Third-Party "
    "Compatibility. Turning that on reverts the plug to KLAP. Your phone must "
    "be on the same network as the plug."
)


def get_state(request: Request) -> AppState:
    """Pull the shared state off the application."""
    return request.app.state.gzplug  # type: ignore[no-any-return]


@router.get("/state")
async def read_state(request: Request) -> dict[str, Any]:
    """Full snapshot, as used on page load."""
    return get_state(request).snapshot()


@router.post("/credentials")
async def set_credentials(request: Request, body: CredentialsIn) -> dict[str, Any]:
    """Store the shared account and reconnect with it."""
    state = get_state(request)
    state.config.username = body.username
    state.config.password = body.password
    state.config.save()
    await state.reload_devices()
    return state.snapshot()


@router.post("/discover")
async def discover(request: Request, body: DiscoverIn) -> dict[str, Any]:
    """Broadcast for plugs, reporting the ones we cannot speak to."""
    state = get_state(request)
    if not state.config.configured:
        raise HTTPException(400, "Set the account credentials first.")

    unsupported: list[dict[str, str]] = []

    async def on_unsupported(error: UnsupportedDeviceError) -> None:
        unsupported.append(
            {"host": error.host or "?", "error": str(error), "help": TPAP_HELP}
        )

    try:
        found = await Discover.discover(
            target=body.target,
            credentials=state.config.credentials,
            discovery_timeout=body.timeout,
            on_unsupported=on_unsupported,
        )
    except KasaException as exc:
        raise HTTPException(502, f"Discovery failed: {exc}") from exc

    devices = [
        {"host": host, "alias": dev.alias, "model": dev.model}
        for host, dev in sorted(found.items())
    ]
    if body.save:
        for host, device in sorted(found.items()):
            if len(state.config.profiles) >= MAX_DEVICES:
                break
            if any(p.config.get("host") == host for p in state.config.profiles):
                continue
            state.config.upsert(BenchProfile.from_device(device))
        state.config.save()
        await state.reload_devices()

    for device in found.values():
        await device.disconnect()

    return {
        "found": devices,
        "unsupported": unsupported,
        "state": state.snapshot(),
    }


@router.post("/devices")
async def add_device(request: Request, body: AddDeviceIn) -> dict[str, Any]:
    """Add one plug by address, for when broadcast cannot reach it."""
    state = get_state(request)
    if not state.config.configured:
        raise HTTPException(400, "Set the account credentials first.")
    if len(state.config.profiles) >= MAX_DEVICES:
        raise HTTPException(400, f"At most {MAX_DEVICES} plugs are supported.")

    try:
        device = await Discover.discover_single(
            body.host,
            credentials=state.config.credentials,
            discovery_timeout=body.timeout,
        )
    except UnsupportedDeviceError as exc:
        raise HTTPException(422, f"{exc}. {TPAP_HELP}") from exc
    except KasaException as exc:
        raise HTTPException(502, f"Could not reach {body.host}: {exc}") from exc

    if device is None:
        raise HTTPException(404, f"No response from {body.host}.")

    try:
        state.config.upsert(BenchProfile.from_device(device, body.label))
        state.config.save()
    finally:
        await device.disconnect()

    await state.reload_devices()
    return state.snapshot()


@router.delete("/devices/{profile_id}")
async def remove_device(request: Request, profile_id: str) -> dict[str, Any]:
    """Forget a bench position."""
    state = get_state(request)
    state.config.remove(profile_id)
    state.config.save()
    await state.reload_devices()
    return state.snapshot()


@router.post("/devices/{profile_id}/reconnect")
async def reconnect_device(request: Request, profile_id: str) -> dict[str, Any]:
    """Retry a plug the operator has just fixed."""
    state = get_state(request)
    try:
        await state.reconnect(profile_id)
    except (RegistryError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return state.snapshot()


@router.post("/devices/{profile_id}/switch")
async def switch_device(
    request: Request, profile_id: str, body: SwitchIn
) -> dict[str, Any]:
    """Flip one relay by hand."""
    state = get_state(request)
    try:
        await state.set_device_state(profile_id, body.on)
    except (RegistryError, KeyError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SessionFault as exc:
        raise HTTPException(502, str(exc)) from exc
    return state.snapshot()


@router.post("/run")
async def start_run(request: Request, body: RunIn) -> dict[str, Any]:
    """Begin a cycle run."""
    state = get_state(request)
    try:
        plan = RunPlan(
            devices=tuple(body.devices),
            cycles=body.cycles,
            on_time_s=body.on_time_s,
            off_time_s=body.off_time_s,
            continue_on_error=body.continue_on_error,
            restore_state=body.restore_state,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        path = await state.start_run(plan)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc

    return {"csv": path.name, "state": state.snapshot()}


@router.post("/run/stop")
async def stop_run(request: Request) -> dict[str, Any]:
    """Stop the current run. The plugs are still restored."""
    state = get_state(request)
    await state.stop_run()
    return state.snapshot()


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    """Past run records, newest first."""
    directory = runs_dir()
    if not directory.exists():
        return []
    files = sorted(directory.glob("run_*.csv"), reverse=True)
    return [
        {"name": f.name, "bytes": f.stat().st_size, "modified": f.stat().st_mtime}
        for f in files[:100]
    ]


@router.get("/runs/{name}")
async def download_run(name: str) -> FileResponse:
    """Download one run record."""
    # Resolve and confine to the runs directory: the name comes from a URL.
    directory = runs_dir().resolve()
    target = (directory / name).resolve()
    if target.parent != directory or not target.is_file():
        raise HTTPException(404, "No such run record.")
    return FileResponse(target, media_type="text/csv", filename=target.name)
