"""Entry point for the frozen build.

PyInstaller freezes a *script*, not a module, so ``gzplug/__main__.py`` cannot
be the target: run as a script it has no package context and its relative
imports fail. This wrapper is imported normally and hands over to the same CLI
the pip install exposes, so ``gzplug.exe run --device ...`` behaves exactly
like ``gzplug run --device ...`` and there is only one interface to document.

Double-clicking the executable passes no arguments, which opens the UI.
"""

from __future__ import annotations

import multiprocessing
import sys

from gzplug.cli import main

if __name__ == "__main__":
    # Windows spawns subprocesses by re-running the executable. Without this,
    # anything that starts a process would relaunch the whole application.
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:] or ["ui"]))
