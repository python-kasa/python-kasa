"""Base class for all module implementations."""
import collections
from abc import ABC, abstractmethod

from kasa import SmartDevice


# TODO: This is used for query construcing
def merge(d, u):
    """Update dict recursively."""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = merge(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class Module(ABC):
    """Base class implemention for all modules.

    The base classes should implement `query` to return the query they want to be
    executed during the regular update cycle.
    """

    def __init__(self, device: "SmartDevice", module: str):
        self._device: "SmartDevice" = device
        self._module = module

    @abstractmethod
    def query(self):
        """Query to execute during the update cycle.

        The inheriting modules implement this to include their wanted
        queries to the query that gets executed when Device.update() gets called.
        """

    @property
    def data(self):
        """Return the module specific raw data from the last update."""
        return self._device._last_update[self._module]

    def call(self, method, params=None):
        """Call the given method with the given parameters."""
        return self._device._query_helper(self._module, method, params)

    def query_for_command(self, query, params=None):
        """Create a request object for the given parameters."""
        return self._device._create_request(self._module, query, params)

    def __repr__(self) -> str:
        return f"<Module {self.__class__.__name__} ({self._module}) for {self._device.alias}>"
