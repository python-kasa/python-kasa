"""FastAPI application factory."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .routes import router
from .state import AppState
from .ws import stream

_LOGGER = logging.getLogger(__name__)


def web_dir() -> Path:
    """Locate the static files, including inside a PyInstaller bundle."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:  # pragma: no cover - packaged builds only
        return Path(bundled) / "gzplug" / "web"
    return Path(__file__).resolve().parent.parent / "web"


def create_app(state: AppState | None = None) -> FastAPI:
    """Build the application, optionally around a pre-made state (tests)."""
    app_state = state or AppState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app_state.startup()
        try:
            yield
        finally:
            await app_state.shutdown()

    app = FastAPI(
        title="gzplug", version=__version__, lifespan=lifespan, docs_url="/api/docs"
    )
    app.state.gzplug = app_state
    app.include_router(router)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await stream(websocket, app_state, app_state.bus)

    static = web_dir()
    if static.is_dir():
        app.mount("/static", StaticFiles(directory=static), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(static / "index.html")
    else:  # pragma: no cover - only if packaging went wrong
        _LOGGER.error("web assets not found at %s", static)

    return app
