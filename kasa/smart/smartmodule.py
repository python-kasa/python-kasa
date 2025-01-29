"""Base implementation for SMART modules."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import TYPE_CHECKING, Any, Concatenate, ParamSpec, TypeVar

from ..exceptions import DeviceError, KasaException, SmartErrorCode
from ..module import Module

if TYPE_CHECKING:
    from .smartdevice import SmartDevice

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T", bound="SmartModule")
_P = ParamSpec("_P")
_R = TypeVar("_R")


def allow_update_after(
    func: Callable[Concatenate[_T, _P], Coroutine[Any, Any, _R]],
) -> Callable[Concatenate[_T, _P], Coroutine[Any, Any, _R]]:
    """Define a wrapper to set _last_update_time to None.

    This will ensure that a module is updated in the next update cycle after
    a value has been changed.
    """

    @wraps(func)
    async def _async_wrap(self: _T, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return await func(self, *args, **kwargs)
        finally:
            self._last_update_time = None

    return _async_wrap


def raise_if_update_error(func: Callable[[_T], _R]) -> Callable[[_T], _R]:
    """Define a wrapper to raise an error if the last module update was an error."""

    @wraps(func)
    def _wrap(self: _T) -> _R:
        if err := self._last_update_error:
            raise err
        return func(self)

    return _wrap


class SmartModule(Module):
    """Base class for SMART modules."""

    NAME: str
    #: Module is initialized, if the given component is available
    REQUIRED_COMPONENT: str | None = None
    #: Module is initialized, if any of the given keys exists in the sysinfo
    SYSINFO_LOOKUP_KEYS: list[str] = []
    #: Query to execute during the main update cycle
    QUERY_GETTER_NAME: str = ""

    REGISTERED_MODULES: dict[str, type[SmartModule]] = {}

    MINIMUM_UPDATE_INTERVAL_SECS = 0
    MINIMUM_HUB_CHILD_UPDATE_INTERVAL_SECS = 60 * 60 * 24

    UPDATE_INTERVAL_AFTER_ERROR_SECS = 30

    DISABLE_AFTER_ERROR_COUNT = 10

    def __init__(self, device: SmartDevice, module: str) -> None:
        self._device: SmartDevice
        super().__init__(device, module)
        self._last_update_time: float | None = None
        self._last_update_error: KasaException | None = None
        self._error_count = 0
        self._logged_remove_keys: list[str] = []

    def __init_subclass__(cls, **kwargs) -> None:
        # We only want to register submodules in a modules package so that
        # other classes can inherit from smartmodule and not be registered
        if cls.__module__.split(".")[-2] == "modules":
            _LOGGER.debug("Registering %s", cls)
            cls.REGISTERED_MODULES[cls._module_name()] = cls

    def _set_error(self, err: Exception | None) -> None:
        if err is None:
            self._error_count = 0
            self._last_update_error = None
        else:
            self._last_update_error = KasaException("Module update error", err)
            self._error_count += 1
            if self._error_count == self.DISABLE_AFTER_ERROR_COUNT:
                _LOGGER.error(
                    "Error processing %s for device %s, module will be disabled: %s",
                    self.name,
                    self._device.host,
                    err,
                )
            if self._error_count > self.DISABLE_AFTER_ERROR_COUNT:
                _LOGGER.error(  # pragma: no cover
                    "Unexpected error processing %s for device %s, "
                    "module should be disabled: %s",
                    self.name,
                    self._device.host,
                    err,
                )

    @property
    def update_interval(self) -> int:
        """Time to wait between updates."""
        if self._last_update_error:
            return self.UPDATE_INTERVAL_AFTER_ERROR_SECS * self._error_count

        if self._device._is_hub_child:
            return self.MINIMUM_HUB_CHILD_UPDATE_INTERVAL_SECS

        return self.MINIMUM_UPDATE_INTERVAL_SECS

    @property
    def disabled(self) -> bool:
        """Return true if the module is disabled due to errors."""
        return self._error_count >= self.DISABLE_AFTER_ERROR_COUNT

    def _should_update(self, update_time: float) -> bool:
        """Return true if module should update based on delay parameters."""
        return (
            not self.update_interval
            or not self._last_update_time
            or (update_time - self._last_update_time) >= self.update_interval
        )

    @classmethod
    def _module_name(cls) -> str:
        return getattr(cls, "NAME", cls.__name__)

    @property
    def name(self) -> str:
        """Name of the module."""
        return self._module_name()

    async def _post_update_hook(self) -> None:  # noqa: B027
        """Perform actions after a device update.

        Any modules overriding this should ensure that self.data is
        accessed unless the module should remain active despite errors.
        """
        assert self.data  # noqa: S101

    def query(self) -> dict:
        """Query to execute during the update cycle.

        Default implementation uses the raw query getter w/o parameters.
        """
        if self.QUERY_GETTER_NAME:
            return {self.QUERY_GETTER_NAME: None}
        return {}

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Call a method.

        Just a helper method.
        """
        return await self._device._query_helper(method, params)

    @property
    def optional_response_keys(self) -> list[str]:
        """Return optional response keys for the module.

        Defaults to no keys. Overriding this and providing keys will remove
        instead of raise on error.
        """
        return []

    @property
    def data(self) -> dict[str, Any]:
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

        remove_keys: list[str] = []
        for data_item in filtered_data:
            if isinstance(filtered_data[data_item], SmartErrorCode):
                if data_item in self.optional_response_keys:
                    remove_keys.append(data_item)
                else:
                    raise DeviceError(
                        f"{data_item} for {self.name}",
                        error_code=filtered_data[data_item],
                    )

        for key in remove_keys:
            if key not in self._logged_remove_keys:
                self._logged_remove_keys.append(key)
                _LOGGER.debug(
                    "Removed key %s from response for device %s as it returned "
                    "error: %s. This message will only be logged once per key.",
                    key,
                    self._device.host,
                    filtered_data[key],
                )

            filtered_data.pop(key)

        if len(filtered_data) == 1 and not remove_keys:
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
