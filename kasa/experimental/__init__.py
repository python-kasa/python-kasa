"""Package for experimental."""

from __future__ import annotations

import os


class Experimental:
    """Class for enabling experimental functionality."""

    _enabled: bool | None = None
    ENV_VAR = "KASA_EXPERIMENTAL"

    @classmethod
    def set_enabled(cls, enabled):
        """Set the enabled value."""
        cls._enabled = enabled

    @classmethod
    def enabled(cls):
        """Get the enabled value."""
        if cls._enabled is not None:
            return cls._enabled

        if env_var := os.getenv(cls.ENV_VAR):
            return env_var.lower() in {"true", "1", "t", "on"}

        return False
