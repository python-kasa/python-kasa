"""Base class for all transport implementations.

All transport classes must derive from this to implement the common interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kasa import DeviceConfig


class BaseTransport(ABC):
    """Base class for all TP-Link protocol transports."""

    DEFAULT_TIMEOUT = 5

    def __init__(
        self,
        *,
        config: DeviceConfig,
    ) -> None:
        """Create a protocol object."""
        self._config = config
        self._host = config.host
        self._port = config.port_override or self.default_port
        self._credentials = config.credentials
        self._credentials_hash = config.credentials_hash
        if not config.timeout:
            config.timeout = self.DEFAULT_TIMEOUT
        self._timeout = config.timeout

    @property
    @abstractmethod
    def default_port(self) -> int:
        """The default port for the transport."""

    @property
    @abstractmethod
    def credentials_hash(self) -> str | None:
        """The hashed credentials used by the transport."""

    @abstractmethod
    async def send(self, request: str) -> dict:
        """Send a message to the device and return a response."""

    @abstractmethod
    async def close(self) -> None:
        """Close the transport.  Abstract method to be overriden."""

    @abstractmethod
    async def reset(self) -> None:
        """Reset internal state."""
