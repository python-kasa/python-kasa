"""Launch the local web UI.

Binds to loopback only. This is a bench tool holding a shared account password
in plaintext; it has no authentication and must not be reachable from the lab
network.

Two entry points, because the UI is reachable two ways and they differ in
whether an event loop is already running: ``gzplug ui`` awaits
:func:`serve` from inside the CLI's loop, while ``python -m gzplug`` and the
frozen executable call :func:`main`, which owns the loop itself. Calling
``uvicorn.run`` from the former nests ``asyncio.run`` and raises.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import threading
import webbrowser

import uvicorn

from .api.app import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _announce(host: str, port: int, open_browser: bool) -> str:
    url = f"http://{host}:{port}/"
    if open_browser:
        # Fires once the server is listening; harmless if a touch early, since
        # the browser retries on reload.
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"gzplug UI on {url}  (Ctrl-C to stop)", flush=True)
    return url


async def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
    verbose: bool = False,
) -> int:
    """Serve the UI on the *current* event loop."""
    _announce(host, port, open_browser)
    config = uvicorn.Config(
        create_app(),
        host=host,
        port=port,
        log_level="debug" if verbose else "warning",
    )
    server = uvicorn.Server(config)
    with contextlib.suppress(KeyboardInterrupt):
        await server.serve()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Serve the UI, owning the event loop. Used by `python -m gzplug`."""
    parser = argparse.ArgumentParser(
        prog="gzplug-ui", description="Bench plug controller (local web UI)."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open a browser."
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(
            serve(
                args.host,
                args.port,
                open_browser=not args.no_browser,
                verbose=args.verbose,
            )
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
