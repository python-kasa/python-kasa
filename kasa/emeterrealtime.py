"""Module for emeter container."""
import logging
from typing import Any, Optional

from pydantic import BaseModel, PositiveFloat, ValidationError, confloat, root_validator

_LOGGER = logging.getLogger(__name__)


class EmeterRealtime(BaseModel):
    """Container for converting different representations of e-meter realtime status data.

    Newer FW/HW versions postfix the variable names with the used units,
    where-as the olders do not have this feature.

    This class automatically converts between these two to allow
    backwards and forwards compatibility.
    """

    # Is it better to have None for missing elements or some default value?
    # We could make current Optional instead

    power: PositiveFloat  # kW (kilo Watts)
    voltage: confloat(ge=0, le=300)  # type: ignore  # V (Volts)
    # current: PositiveFloat = 0  # A (Amps) - Some devices don't return current
    current: Optional[PositiveFloat]  # A (Amps) - Some devices don't return current
    total: PositiveFloat  # kWh (kilo Watt hours)

    @property
    def power_mw(self) -> float:
        """Return power in milli watts (mW)."""
        return int(self.power * 1000)

    @property
    def voltage_mv(self) -> float:
        """Return voltage in volts (V)."""
        return int(self.voltage * 1000)

    @property
    def current_ma(self) -> Optional[float]:
        """Return current in amps (A)."""
        return int(self.current * 1000) if self.current else None

    @property
    def total_wh(self) -> float:
        """Return total power in watt hours (Wh)."""
        return int(self.total * 1000)

    def __repr__(self):
        return f"<EmeterRealtime power={self.power} kW voltage={self.voltage} V current={self.current} A total={self.total} kWh>"

    class Config:
        """Configuration for pydantic DataModel."""

        validate_assignment = True
        # Note: default configuration of pydantic will ignore unrecognised attributes

    @root_validator(pre=True)
    def _convert_scaled(cls, values: dict[str, Any]) -> dict[str, Any]:
        scaled_keys = ["power_mw", "voltage_mv", "current_ma", "total_wh"]

        for scaled_key in scaled_keys:
            unscaled_key = scaled_key[: scaled_key.find("_")]

            unscaled = values.get(unscaled_key)
            scaled = values.get(scaled_key)

            if unscaled is None and scaled is not None:
                values[unscaled_key] = scaled / 1000

            # Note: if both scaled and unscaled are None the regular field validator will deal with it
            # We don't need to worry about both being set

        return values


def test():
    """Draft test code for EmeterRealtime class."""
    print(
        repr(
            EmeterRealtime.parse_obj(
                {"power": 0.035, "voltage": 220, "current": 0.16, "total_wh": 840}
            )
        )
    )
    print(
        repr(
            EmeterRealtime.parse_obj(
                {
                    "power": 0.035,
                    "voltage": 220,
                    "total_wh": 840,
                }  # Should allow current to be missing and set it to 0
            )
        )
    )
    print(
        repr(
            EmeterRealtime.parse_obj(
                {"power_mw": 35, "voltage_mv": 225000, "current_ma": 160, "total": 0.84}
            )
        )
    )
    print()

    try:
        EmeterRealtime.parse_obj({"power": 0.035, "voltage": 220})
    except ValidationError as e:
        print(e)
    print("Error expected")


if __name__ == "__main__":
    test()
