"""Base class for IOT module implementations."""
import collections
import logging
from ...feature import Feature

from ..exceptions import SmartDeviceException
from ..module import Module

_LOGGER = logging.getLogger(__name__)


# TODO: This is used for query constructing, check for a better place
def merge(d, u):
    """Update dict recursively."""
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = merge(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class IotModule(Module):
    """Base class implemention for all IOT modules."""
    def add_feature(self, feature: Feature):
        """Add module feature."""
        feature_name = f"{self._module}_{feature.name}"
        if feature_name in self._module_features:
            raise SmartDeviceException("Duplicate name detected %s" % feature_name)
        self._module_features[feature_name] = feature

    @property
    def estimated_query_response_size(self):
        """Estimated maximum size of query response.

        The inheriting modules implement this to estimate how large a query response
        will be so that queries can be split should an estimated response be too large
        """
        return 256  # Estimate for modules that don't specify

    def call(self, method, params=None):
        """Call the given method with the given parameters."""
        return self._device._query_helper(self._module, method, params)

    def query_for_command(self, query, params=None):
        """Create a request object for the given parameters."""
        return self._device._create_request(self._module, query, params)

    @property
    def data(self):
        """Return the module specific raw data from the last update."""
        if self._module not in self._device._last_update:
            raise SmartDeviceException(
                f"You need to call update() prior accessing module data"
                f" for '{self._module}'"
            )

        return self._device._last_update[self._module]

    @property
    def is_supported(self) -> bool:
        """Return whether the module is supported by the device."""
        if self._module not in self._device._last_update:
            _LOGGER.debug("Initial update, so consider supported: %s", self._module)
            return True

        return "err_code" not in self.data
