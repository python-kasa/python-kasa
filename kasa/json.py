"""JSON abstraction."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import orjson

    def dumps(obj: Any, *, default: Callable | None = None) -> str:
        """Dump JSON."""
        return orjson.dumps(obj).decode()

    loads = orjson.loads
except ImportError:
    import json

    def dumps(obj: Any, *, default: Callable | None = None) -> str:
        """Dump JSON."""
        # Separators specified for consistency with orjson
        return json.dumps(obj, separators=(",", ":"))

    loads = json.loads


try:
    from mashumaro.mixins.orjson import DataClassORJSONMixin

    DataClassJSONMixin = DataClassORJSONMixin
except ImportError:
    from mashumaro.mixins.json import DataClassJSONMixin as JSONMixin

    DataClassJSONMixin = JSONMixin  # type: ignore[assignment, misc]
