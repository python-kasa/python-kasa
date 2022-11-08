"""Wrappers classes for stats returned from Usage module get_daystat and get_monthstat."""
import logging
from typing import Any, List, Optional

from pydantic import BaseModel, PositiveFloat, ValidationError, conint, root_validator

_LOGGER = logging.getLogger(__name__)


class UsageStat(BaseModel):
    """Pydantic model for validating and converting different representations of monthly and daily usage stats.

    Note: default configuration of pydantic will ignore unrecognised attributes
    """

    # Note: mypy complains about a type problem when using pydantic types
    # and there doesn't seem to be a good workaround, hence the type: ignore
    # https://github.com/pydantic/pydantic/issues/239
    year: conint(ge=1970, le=2100)  # type: ignore
    month: conint(ge=1, le=12)  # type: ignore
    day: Optional[conint(ge=1, le=31)]  # type: ignore
    time: conint(ge=0, le=44640)  # type: ignore

    @property
    def is_monthly(self):
        """Return True if this is a stat for a month (no day value)."""
        return self.day is None

    @property
    def is_daily(self):
        """Return True if this is a stat for a day (has a day value)."""
        return not self.is_monthly

    def datekv(self):
        """Return key,value pair for period index, time."""
        return self.day if self.is_daily else self.month, self.time

    def __repr__(self):
        return f"<UsageStat {self.year:04}-{self.month:02}{f'-{self.day:02}' if self.is_daily else ''} {self.time} mins>"


class EmeterStat(BaseModel):
    """Pydantic model for validating and converting different representations of monthly and daily e-meter stats.

    Newer FW/HW versions postfix the energy variable name with the used units,
    where-as the olders do not have this feature.

    This class automatically handles the formats for backwards and
    forwards compatibility.
    """

    year: conint(ge=1970, le=3000)  # type: ignore
    month: conint(ge=1, le=12)  # type: ignore
    day: Optional[conint(ge=1, le=31)]  # type: ignore
    energy: PositiveFloat  # type: ignore # kW (kilo Watts)

    @property
    def is_monthly(self) -> bool:
        """Return True if this is a stat for a month (no day value)."""
        return self.day is None

    @property
    def is_daily(self) -> bool:
        """Return True if this is a stat for a day (has a day value)."""
        return not self.is_monthly

    @property
    def energy_wh(self) -> int:
        """Return energy in watt hours."""
        return int(self.energy * 1000)

    #    @energy_wh.setter
    #    def energy_wh(self, energy_wh):
    #        self.energy = energy_wh / 1000

    def datekv(self, *, kwh: bool = True):
        """Return key,value pair for period index, energy."""
        k = self.day if self.is_daily else self.month
        v = self.energy if kwh else int(self.energy * 1000)
        return k, v

    def __repr__(self):
        return f"<EmeterStat {self.year:04}-{self.month:02}{f'-{self.day:02}' if self.is_daily else ''} {self.energy} kWh>"

    class Config:
        """Configuration for pydantic DataModel."""

        validate_assignment = True
        # Note: default configuration of pydantic will ignore unrecognised attributes

    @root_validator(pre=True)
    def _convert_energy(cls, values: dict[str, Any]) -> dict[str, Any]:
        energy = values.get("energy")
        energy_wh = values.get("energy_wh")
        if energy is None:
            if energy_wh is None:
                return values  # regular field validation will raise an error
            values["energy"] = energy_wh / 1000
        return values


class EmeterRealtime(BaseModel):
    """Container for converting different representations of e-meter realtime status data.

    Newer FW/HW versions postfix the variable names with the used units,
    where-as the olders do not have this feature.

    This class automatically converts between these two to allow
    backwards and forwards compatibility.

    """

    power: PositiveFloat  # kW (kilo Watts)
    voltage: PositiveFloat  # V (Volts)
    current: PositiveFloat = 0  # A (Amps) - Some devices don't return current
    total: PositiveFloat  # kWh (kilo Watt hours)

    @property
    def power_mw(self):
        """Return power in milli watts (mW)."""
        return int(self.power * 1000)

    # @power_mw.setter
    # def power_mw(self, mw):
    #    self.power = mw / 1000

    @property
    def voltage_mv(self):
        """Return voltage in volts (V)."""
        return int(self.voltage * 1000)

    # @voltage_mv.setter
    # def voltage_mv(self, mv):
    #    self.voltage = mv / 1000

    @property
    def current_ma(self):
        """Return current in amps (A)."""
        return int(self.current * 1000)

    # @current_ma.setter
    # def current_ma(self, ma):
    #    self.current = ma / 1000

    @property
    def total_wh(self):
        """Return total power in watt hours (Wh)."""
        return int(self.total * 1000)

    # @total_wh.setter
    # def total_wh(self, wh):
    #    self.total = wh / 1000

    def __repr__(self):
        return f"<EmeterStatus power={self.power} kW voltage={self.voltage} V current={self.current} A total={self.total} kWh>"

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


def test() -> None:
    """Test pydantic models."""
    print(repr(UsageStat.parse_obj({"year": 2022, "month": 11, "day": 1, "time": 45})))
    print(repr(UsageStat.parse_obj({"year": 2022, "month": 11, "time": 45 * 30})))
    print()

    usage_stat_list = [
        {"year": 2022, "month": 9, "time": 3},
        {"year": 2022, "month": 10, "time": 4},
        {"year": 2022, "month": 11, "time": 5},
    ]
    usl = dict(UsageStat(**x).datekv() for x in usage_stat_list)
    print(repr(usl))
    print()

    try:
        UsageStat.parse_obj({"year": 2022, "month": 11, "day": 5})
    except ValidationError as e:
        print(e)
    print("Error expected")
    print()

    print(
        repr(
            EmeterStat.parse_obj(
                {"year": 2022, "month": 11, "day": 1, "energy_wh": 500}
            )
        )
    )
    print(repr(EmeterStat.parse_obj({"year": 2022, "month": 11, "energy": 3})))
    print()

    emeter_stat_list: List[dict] = [
        {"year": 2022, "month": 9, "energy": 0.3},
        {"year": 2022, "month": 10, "energy_wh": 400},
        {"year": 2022, "month": 11, "energy": 0.5},
    ]
    usl = dict(EmeterStat(**x).datekv() for x in emeter_stat_list)
    print(repr(usl))
    print()

    try:
        EmeterStat.parse_obj({"year": 2022, "month": 11, "day": 5})
    except ValidationError as e:
        print(e)
    print("Error expected")
    print()

    try:
        # Currently if both provided we'll use the kwh one
        es = EmeterStat.parse_obj(
            {"year": 2022, "month": 11, "day": 5, "energy_wh": 500, "energy": 1.5}
        )
        print(repr(es))
    except ValidationError as e:
        print("Unexpected error")
        print(e)
    if es.energy_wh != 1500:
        print("Unexpected value for energy_wh")
    print()

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
