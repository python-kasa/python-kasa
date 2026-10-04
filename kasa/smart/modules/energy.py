"""Implementation of energy monitoring module."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, NoReturn

from ...emeterstatus import EmeterStatus
from ...exceptions import DeviceError, KasaException, SmartErrorCode
from ...interfaces.energy import Energy as EnergyInterface
from ..smartmodule import SmartModule, raise_if_update_error

_OPTIONAL_METHOD_ERRORS = {
    SmartErrorCode.PARAMS_ERROR,
    SmartErrorCode.UNKNOWN_METHOD_ERROR,
}

# get_energy_data interval values, in minutes.
_ENERGY_DATA_INTERVAL_DAILY = 1440
_ENERGY_DATA_INTERVAL_MONTHLY = 43200


class Energy(SmartModule, EnergyInterface):
    """Implementation of energy monitoring module."""

    REQUIRED_COMPONENT = "energy_monitoring"

    _energy: dict[str, Any]
    _current_consumption: float | None

    def _get_current_power_mw(
        self, data: dict[str, Any], energy: dict[str, Any] | None = None
    ) -> float | None:
        """Return the best available current power reading in milliwatts."""
        energy = self._energy if energy is None else energy

        if (power := data.get("get_emeter_data", {}).get("power_mw")) is not None:
            return power

        # Prefer the higher precision milliwatt readings from the energy usage
        # payload. get_current_power is only a lower precision fallback used by
        # devices such as P304M whose get_energy_usage omits current_power.
        if (power := energy.get("current_power")) is not None:
            return power

        if (
            power := data.get("get_current_power", {}).get("current_power")
        ) is not None:
            return power * 1_000

        return None

    async def _post_update_hook(self) -> None:
        try:
            data = self.data
        except DeviceError as de:
            self._energy = {}
            self._current_consumption = None
            raise de

        # If version is 1 then data is get_energy_usage
        self._energy = data.get("get_energy_usage", data)

        if "voltage_mv" in data.get("get_emeter_data", {}):
            self._supported = (
                self._supported | EnergyInterface.ModuleFeature.VOLTAGE_CURRENT
            )

        # Energy monitoring v2 devices expose historical stats via
        # get_energy_data. Hardware-verified on KP125M; see PR discussion for
        # confirmation on other v2 models.
        if self.supported_version >= 2:
            self._supported = (
                self._supported | EnergyInterface.ModuleFeature.PERIODIC_STATS
            )

        if (power := self._get_current_power_mw(data)) is not None:
            self._current_consumption = power / 1_000
        else:
            self._current_consumption = None

    def query(self) -> dict:
        """Query to execute during the update cycle."""
        req = {
            "get_energy_usage": None,
        }
        if self.supported_version > 1:
            req["get_current_power"] = None
            req["get_emeter_data"] = None
            req["get_emeter_vgain_igain"] = None
        return req

    @property
    def optional_response_keys(self) -> list[str]:
        """Return optional response keys for the module."""
        if self.supported_version > 1:
            return ["get_energy_usage", "get_current_power"]
        return []

    @property
    def current_consumption(self) -> float | None:
        """Current power in watts."""
        return self._current_consumption

    @property
    def energy(self) -> dict:
        """Return get_energy_usage results."""
        return self._energy

    def _get_status_from_energy(
        self, energy: dict[str, Any], power_mw: float | None = None
    ) -> EmeterStatus:
        return EmeterStatus(
            {
                "power_mw": (
                    power_mw if power_mw is not None else energy.get("current_power")
                ),
                "total": energy.get("today_energy", 0) / 1_000,
            }
        )

    @property
    @raise_if_update_error
    def status(self) -> EmeterStatus:
        """Get the emeter status."""
        data = self.data
        if "get_emeter_data" in data:
            return EmeterStatus(data["get_emeter_data"])

        return self._get_status_from_energy(
            self.energy, self._get_current_power_mw(data)
        )

    async def get_status(self) -> EmeterStatus:
        """Return real-time statistics."""
        if self.supported_version > 1:
            try:
                res = await self.call("get_emeter_data")
            except DeviceError as ex:
                if ex.error_code not in _OPTIONAL_METHOD_ERRORS:
                    raise
            else:
                return EmeterStatus(res["get_emeter_data"])

        energy: dict[str, Any] = {}
        try:
            res = await self.call("get_energy_usage")
        except DeviceError:
            if self.supported_version <= 1:
                raise
        else:
            energy = res["get_energy_usage"]
            if energy.get("current_power") is not None:
                return self._get_status_from_energy(energy)

        current_power: dict[str, Any] = {}
        if self.supported_version > 1:
            try:
                res = await self.call("get_current_power")
            except DeviceError as ex:
                if ex.error_code not in _OPTIONAL_METHOD_ERRORS:
                    raise
            else:
                current_power = res["get_current_power"]

        return self._get_status_from_energy(
            energy,
            self._get_current_power_mw({"get_current_power": current_power}, energy),
        )

    @property
    def consumption_this_month(self) -> float | None:
        """Get the emeter value for this month in kWh."""
        if (month := self.energy.get("month_energy")) is not None:
            return month / 1_000
        return None

    @property
    def consumption_today(self) -> float | None:
        """Get the emeter value for today in kWh."""
        if (today := self.energy.get("today_energy")) is not None:
            return today / 1_000
        return None

    @property
    @raise_if_update_error
    def consumption_total(self) -> float | None:
        """Return total consumption since last reboot in kWh."""
        return None

    @property
    @raise_if_update_error
    def current(self) -> float | None:
        """Return the current in A."""
        if (ma := self.data.get("get_emeter_data", {}).get("current_ma")) is not None:
            return ma / 1_000
        return None

    @property
    @raise_if_update_error
    def voltage(self) -> float | None:
        """Get the current voltage in V."""
        if (mv := self.data.get("get_emeter_data", {}).get("voltage_mv")) is not None:
            return mv / 1_000
        return None

    async def _deprecated_get_realtime(self) -> EmeterStatus:
        """Retrieve current energy readings."""
        return self.status

    async def erase_stats(self) -> NoReturn:
        """Erase all stats."""
        raise KasaException("Device does not support erasing statistics")

    async def _query_energy_data(
        self, start_timestamp: int, end_timestamp: int, interval: int
    ) -> list[int]:
        """Return raw ``get_energy_data`` buckets for a time window.

        The firmware may answer with a response whose ``end_timestamp`` is
        earlier than requested. In that case it is re-queried starting from
        that timestamp and the returned ``data`` arrays are concatenated,
        matching the behaviour of the official app.
        """
        cursor = start_timestamp
        data: list[int] = []
        while cursor < end_timestamp:
            res = await self.call(
                "get_energy_data",
                {
                    "start_timestamp": cursor,
                    "end_timestamp": end_timestamp,
                    "interval": interval,
                },
            )
            payload = res["get_energy_data"]
            data.extend(payload["data"])
            page_end = payload.get("end_timestamp", end_timestamp)
            # Stop when the window is covered or the cursor stops advancing.
            if page_end >= end_timestamp or page_end <= cursor:
                break
            cursor = page_end
        return data

    async def get_daily_stats(
        self, *, year: int | None = None, month: int | None = None, kwh: bool = True
    ) -> dict:
        """Return daily stats for the given year & month.

        The return value is a dictionary of ``{day: energy, ...}`` where energy
        is in kWh, or Wh when ``kwh`` is ``False``.
        """
        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        # get_energy_data returns daily buckets one quarter at a time, so query
        # the quarter containing the requested month and keep that month's days.
        quarter_start_month = ((month - 1) // 3) * 3 + 1
        start_dt = datetime(year, quarter_start_month, 1)
        if quarter_start_month == 10:
            end_dt = datetime(year + 1, 1, 1)
        else:
            end_dt = datetime(year, quarter_start_month + 3, 1)

        data = await self._query_energy_data(
            int(start_dt.timestamp()),
            int(end_dt.timestamp()),
            _ENERGY_DATA_INTERVAL_DAILY,
        )

        scale = 1 / 1_000 if kwh else 1
        result: dict[int, float] = {}
        for offset, value in enumerate(data):
            bucket = start_dt + timedelta(days=offset)
            if bucket.year == year and bucket.month == month:
                result[bucket.day] = value * scale
        return result

    async def get_monthly_stats(
        self, *, year: int | None = None, kwh: bool = True
    ) -> dict:
        """Return monthly stats for the given year.

        The return value is a dictionary of ``{month: energy, ...}`` where
        energy is in kWh, or Wh when ``kwh`` is ``False``.
        """
        if year is None:
            year = datetime.now().year

        start_dt = datetime(year, 1, 1)
        end_dt = datetime(year + 1, 1, 1)
        data = await self._query_energy_data(
            int(start_dt.timestamp()),
            int(end_dt.timestamp()),
            _ENERGY_DATA_INTERVAL_MONTHLY,
        )

        scale = 1 / 1_000 if kwh else 1
        return {month: value * scale for month, value in enumerate(data[:12], start=1)}

    async def _check_supported(self) -> bool:
        """Additional check to see if the module is supported by the device."""
        # Energy module is not supported on P304M parent device
        return "device_on" in self._device.sys_info
