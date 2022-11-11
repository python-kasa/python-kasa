"""Wrappers class for stats returned from Usage module get_daystat and get_monthstat."""
import logging
from typing import Any, List, Optional

from pydantic import BaseModel, PositiveFloat, ValidationError, conint, root_validator

_LOGGER = logging.getLogger(__name__)


class DayMonthStat(BaseModel):
    """Pydantic model for validating and converting different representations of monthly and daily device stats.

    Note: default configuration of pydantic will ignore unrecognised attributes when initialising or assigning
    """

    # Note: mypy complains about a type problem when using pydantic types
    # and there doesn't seem to be a good workaround, hence the type: ignore
    # https://github.com/pydantic/pydantic/issues/239

    year: conint(ge=1970, le=2100)  # type: ignore
    month: conint(ge=1, le=12)  # type: ignore
    day: Optional[conint(ge=1, le=31)]  # type: ignore

    @property
    def is_monthly(self):
        """Return True if this is a stat for a month (no day value) ie from get_monthstat."""
        return self.day is None

    @property
    def is_daily(self):
        """Return True if this is a stat for a day (has a day value) ie from get_daystat."""
        return not self.is_monthly

    def datekv(self):
        """Return key,value pair for period index, time."""
        return 0, 0

    def __repr__(self):
        return f"<BaseStat {self.year:04}-{self.month:02}{f'-{self.day:02}' if self.is_daily else ''} no data >"


class UsageStat(DayMonthStat):
    """Pydantic model for validating and converting different representations of monthly and daily usage stats."""

    time: conint(ge=0, le=44640)  # type: ignore

    def datekv(self):
        """Return key,value pair for period index, time."""
        return self.day if self.is_daily else self.month, self.time

    def __repr__(self):
        return f"<UsageStat {self.year:04}-{self.month:02}{f'-{self.day:02}' if self.is_daily else ''} {self.time} mins>"


class EmeterStat(DayMonthStat):
    """Pydantic model for validating and converting different representations of monthly and daily e-meter stats.

    Newer FW/HW versions postfix the energy variable name with the used units,
    where-as the olders do not have this feature. (example: old = energy, new = energy_wh)

    This class automatically handles the formats for backwards and
    forwards compatibility.
    """

    energy: PositiveFloat  # type: ignore # kW (kilo Watts)

    @property
    def energy_wh(self) -> int:
        """Return energy in watt hours."""
        return int(self.energy * 1000)

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


if __name__ == "__main__":
    test()
