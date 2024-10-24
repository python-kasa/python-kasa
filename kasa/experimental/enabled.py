"""Package for experimental enabled."""


class Enabled:
    """Class for enabling experimental functionality."""

    value = False

    @classmethod
    def set(cls, value):
        """Set the enabled value."""
        cls.value = value
