"""JSON abstraction."""

try:
    import orjson

    def dumps(obj, *, default=None):
        """Dump JSON."""
        return orjson.dumps(obj).decode()

    loads = orjson.loads
except ImportError:
    import json

    dumps = json.dumps
    loads = json.loads
