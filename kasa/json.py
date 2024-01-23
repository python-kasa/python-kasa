"""JSON abstraction."""

try:
    import orjson

    def dumps(obj, *, default=None):
        """Dump JSON."""
        return orjson.dumps(obj).decode()

    loads = orjson.loads
except ImportError:
    import json

    def dumps(obj, *, default=None):
        """Dump JSON."""
        return json.dumps(obj, separators=(",", ":"))

    loads = json.loads
