"""Package for experimental enabled."""

from __future__ import annotations

import os


class Enabled:
    """Class for enabling experimental functionality."""

    _value: bool | None = None
    ENV_VAR = "KASA_EXPERIMENTAL"

    @classmethod
    def set(cls, value):
        """Set the enabled value."""
        cls._value = value

    @classmethod
    def get(cls):
        """Get the enabled value."""
        if cls._value is not None:
            return cls._value

        if env_var := os.getenv(cls.ENV_VAR):
            return env_var.lower() in {"true", "1", "t", "on"}

        return False
