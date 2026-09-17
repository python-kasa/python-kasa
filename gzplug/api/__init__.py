"""HTTP and WebSocket layer over :mod:`gzplug.core`.

Nothing here contains device logic. Routes translate requests into calls on
:class:`~gzplug.api.state.AppState`, and the browser is kept current by a
WebSocket that is simply another subscriber on the same event bus the CSV
logger uses.
"""

from __future__ import annotations
