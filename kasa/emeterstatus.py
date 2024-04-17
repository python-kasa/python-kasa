"""Module for emeter container."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)


class EmeterStatus(dict):
    """Container for converting different representations of emeter data.

    Newer FW/HW versions postfix the variable names with the used units,
    where-as the olders do not have this feature.

    This class automatically converts between these two to allow
    backwards and forwards compatibility.
    """

    @property
    def voltage(self) -> float | None:
        """Return voltage in V."""
        try:
            return self["voltage"]
        except ValueError:
            return None

    @property
    def power(self) -> float | None:
        """Return power in W."""
        try:
            return self["power"]
        except ValueError:
            return None

    @property
    def current(self) -> float | None:
        """Return current in A."""
        try:
            return self["current"]
        except ValueError:
            return None

    @property
    def total(self) -> float | None:
        """Return total in kWh."""
        try:
            return self["total"]
        except ValueError:
            return None

    def __repr__(self):
        return (
            f"<EmeterStatus power={self.power} voltage={self.voltage}"
            f" current={self.current} total={self.total}>"
        )

    def __getitem__(self, item):
        """Return value in wanted units."""
        valid_keys = [
            "voltage_mv",
            "power_mw",
            "current_ma",
            "energy_wh",
            "total_wh",
            "voltage",
            "power",
            "current",
            "total",
            "energy",
        ]

        # 1. if requested data is available, return it
        if item in super().keys():  # noqa: SIM118
            return super().__getitem__(item)
        # otherwise decide how to convert it
        else:
            if item not in valid_keys:
                raise KeyError(item)
            if "_" in item:  # upscale
                return super().__getitem__(item[: item.find("_")]) * 1000
            else:  # downscale
                for i in super().keys():  # noqa: SIM118
                    if (
                        i.startswith(item)
                        and (value := self.__getitem__(i)) is not None
                    ):
                        return value / 1000

                _LOGGER.debug(f"Unable to find value for '{item}'")
                return None
