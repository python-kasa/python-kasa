"""Module for base light effect module."""

from __future__ import annotations

from ..module import Module


class LedModule(Module):
    """Base interface to represent a LED module."""

    # This needs to implement abstract methods for typing to work with
    # overload get_module(type[ModuleT]) -> ModuleT:
    # https://discuss.python.org/t/add-abstracttype-to-the-typing-module/21996

    @property
    def led(self) -> bool:
        """Return current led status."""
        raise NotImplementedError()

    async def set_led(self, enable: bool) -> None:
        """Set led."""
        raise NotImplementedError()

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        raise NotImplementedError()

    @property
    def data(self):
        """Query to execute during the update cycle."""
        raise NotImplementedError()
