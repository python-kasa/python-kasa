"""Implementation of homekit module.

Currently only useful to check if device supports homekit.
"""

from __future__ import annotations

from ..smartcammodule import SmartCamModule


class HomeKit(SmartCamModule):
    """Implementation of homekit module.

    Currently only useful to check if device supports homekit.
    """

    # Rename/Remove NAME when implementing common interface
    NAME = "SmartHomeKit"
    REQUIRED_COMPONENT = "homekit"

    @property
    def info(self) -> dict[str, str]:
        """Not supported, return empty dict."""
        return {}
