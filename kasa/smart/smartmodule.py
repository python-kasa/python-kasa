"""Base implementation for SMART modules."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import TYPE_CHECKING, Any

from typing_extensions import Concatenate, ParamSpec, TypeVar

from ..exceptions import DeviceError, KasaException, SmartErrorCode
from ..module import Module

if TYPE_CHECKING:
    from .smartdevice import SmartDevice

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T", bound="SmartModule")
_P = ParamSpec("_P")


def update_after(
    func: Callable[Concatenate[_T, _P], Awaitable[None]],
) -> Callable[Concatenate[_T, _P], Coroutine[Any, Any, None]]:
    """Define a wrapper to set _last_update_time to None.

    This will ensure that a module is updated in the next update cycle after
    a value has been changed.
    """

    async def _async_wrap(self: _T, *args: _P.args, **kwargs: _P.kwargs) -> None:
        try:
            await func(self, *args, **kwargs)
        finally:
            self._last_update_time = None

    return _async_wrap


class SmartModule(Module):
    """Base class for SMART modules."""

    NAME: str
    #: Module is initialized, if the given component is available
    REQUIRED_COMPONENT: str | None = None
    #: Module is initialized, if the given key available in the main sysinfo
    REQUIRED_KEY_ON_PARENT: str | None = None
    #: Query to execute during the main update cycle
    QUERY_GETTER_NAME: str

    REGISTERED_MODULES: dict[str, type[SmartModule]] = {}

    def __init__(self, device: SmartDevice, module: str):
        self._device: SmartDevice
        super().__init__(device, module)
        self._last_update_time: float | None = None

    def __init_subclass__(cls, **kwargs):
        name = getattr(cls, "NAME", cls.__name__)
        _LOGGER.debug("Registering %s" % cls)
        cls.REGISTERED_MODULES[name] = cls

    @property
    def name(self) -> str:
        """Name of the module."""
        return getattr(self, "NAME", self.__class__.__name__)

    def _post_update_hook(self):  # noqa: B027
        """Perform actions after a device update.

        Any modules overriding this should ensure that self.data is
        accessed unless the module should remain active despite errors.
        """
        assert self.data  # noqa: S101

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        return {self.QUERY_GETTER_NAME: None}

    def call(self, method, params=None):
        """Call a method.

        Just a helper method.
        """
        return self._device._query_helper(method, params)

    @property
    def data(self):
        """Return response data for the module.

        If the module performs only a single query, the resulting response is unwrapped.
        If the module does not define a query, this property returns a reference
        to the main "get_device_info" response.
        """
        dev = self._device
        q = self.query()

        if not q:
            return dev.sys_info

        q_keys = list(q.keys())
        query_key = q_keys[0]

        # TODO: hacky way to check if update has been called.
        #  The way this falls back to parent may not always be wanted.
        #  Especially, devices can have their own firmware updates.
        if query_key not in dev._last_update:
            if dev._parent and query_key in dev._parent._last_update:
                _LOGGER.debug("%s not found child, but found on parent", query_key)
                dev = dev._parent
            else:
                raise KasaException(
                    f"You need to call update() prior accessing module data"
                    f" for '{self._module}'"
                )

        filtered_data = {k: v for k, v in dev._last_update.items() if k in q_keys}

        for data_item in filtered_data:
            if isinstance(filtered_data[data_item], SmartErrorCode):
                raise DeviceError(
                    f"{data_item} for {self.name}", error_code=filtered_data[data_item]
                )
        if len(filtered_data) == 1:
            return next(iter(filtered_data.values()))

        return filtered_data

    @property
    def supported_version(self) -> int:
        """Return version supported by the device.

        If the module has no required component, this will return -1.
        """
        if self.REQUIRED_COMPONENT is not None:
            return self._device._components[self.REQUIRED_COMPONENT]
        return -1

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device.

        Used for parents who report components on the parent that are only available
        on the child or for modules where the device has a pointless component like
        color_temp_range but only supports one value.
        """
        return True

    def _has_data_error(self) -> bool:
        try:
            assert self.data  # noqa: S101
            return False
        except DeviceError:
            return True
