"""Implementation of homekit module."""

from __future__ import annotations

from ..smartcammodule import SmartCamModule


class HomeKit(SmartCamModule):
    """Implementation of homekit module."""

    REQUIRED_COMPONENT = "homekit"

    @property
    def info(self) -> dict[str, str]:
        """Not supported, return empty dict."""
        return {}
