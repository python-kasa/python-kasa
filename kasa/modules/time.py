"""Provides the current time and timezone information."""
from datetime import datetime

from ..exceptions import SmartDeviceException
from .module import Module, merge

timezones = [
    {
        "index": 0,
        "zone_str": "(UTC-12:00) International Date Line West",
        "tz_str": "<GMT+12>12",
        "dst_offset": 0,
    },
    {
        "index": 1,
        "zone_str": "(UTC-11:00) Coordinated Universal Time-11",
        "tz_str": "<GMT+11>11",
        "dst_offset": 0,
    },
    {
        "index": 2,
        "zone_str": "(UTC-10:00) Hawaii",
        "tz_str": "HST10",
        "dst_offset": 0,
    },
    {
        "index": 3,
        "zone_str": "(UTC-09:00) Alaska",
        "tz_str": "AKST9AKDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 4,
        "zone_str": "(UTC-08:00) Baja California",
        "tz_str": "PST8PDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 5,
        "zone_str": "(UTC-08:00) Pacific Standard Time (US & Canada)",
        "tz_str": "PST8",
        "dst_offset": 0,
    },
    {
        "index": 6,
        "zone_str": "(UTC-08:00) Pacific Daylight Time (US & Canada)",
        "tz_str": "PST8PDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 7,
        "zone_str": "(UTC-07:00) Arizona",
        "tz_str": "MST7",
        "dst_offset": 0,
    },
    {
        "index": 8,
        "zone_str": "(UTC-07:00) Chihuahua, La Paz, Mazatlan",
        "tz_str": "MST7MDT,M4.1.0,M10.5.0",
        "dst_offset": 60,
    },
    {
        "index": 9,
        "zone_str": "(UTC-07:00) Mountain Standard Time (US & Canada)",
        "tz_str": "MST7",
        "dst_offset": 0,
    },
    {
        "index": 10,
        "zone_str": "(UTC-07:00) Mountain Daylight Time (US & Canada)",
        "tz_str": "MST7MDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 11,
        "zone_str": "(UTC-06:00) Central America",
        "tz_str": "CST6",
        "dst_offset": 0,
    },
    {
        "index": 12,
        "zone_str": "(UTC-06:00) Central Standard Time (US & Canada)",
        "tz_str": "CST6",
        "dst_offset": 0,
    },
    {
        "index": 13,
        "zone_str": "(UTC-06:00) Central Daylight Time (US & Canada)",
        "tz_str": "CST6CDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 14,
        "zone_str": "(UTC-06:00) Guadalajara, Mexico City, Monterrey",
        "tz_str": "CST6CDT,M4.1.0,M10.5.0",
        "dst_offset": 60,
    },
    {
        "index": 15,
        "zone_str": "(UTC-06:00) Saskatchewan",
        "tz_str": "<GMT+6>6",
        "dst_offset": 0,
    },
    {
        "index": 16,
        "zone_str": "(UTC-05:00) Bogota, Lima, Quito, Rio Branco",
        "tz_str": "COT5",
        "dst_offset": 0,
    },
    {
        "index": 17,
        "zone_str": "(UTC-05:00) Eastern Standard Time (US & Canada)",
        "tz_str": "EST5",
        "dst_offset": 0,
    },
    {
        "index": 18,
        "zone_str": "(UTC-05:00) Eastern Daylight Time (US & Canada)",
        "tz_str": "EST5EDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 19,
        "zone_str": "(UTC-05:00) Indiana (East)",
        "tz_str": "EST5EDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 20,
        "zone_str": "(UTC-04:30) Caracas",
        "tz_str": "VET4:30",
        "dst_offset": 0,
    },
    {
        "index": 21,
        "zone_str": "(UTC-04:00) Asuncion",
        "tz_str": "PYT4PYST,M10.1.0/0,M3.4.0/0",
        "dst_offset": 60,
    },
    {
        "index": 22,
        "zone_str": "(UTC-04:00) Atlantic Standard Time (Canada)",
        "tz_str": "AST4",
        "dst_offset": 0,
    },
    {
        "index": 23,
        "zone_str": "(UTC-04:00) Atlantic Daylight Time (Canada)",
        "tz_str": "AST4ADT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 24,
        "zone_str": "(UTC-04:00) Cuiaba",
        "tz_str": "AMT4AMST,M10.3.0/0,M2.3.0/0",
        "dst_offset": 60,
    },
    {
        "index": 25,
        "zone_str": "(UTC-04:00) Georgetown, La Paz, Manaus, San Juan",
        "tz_str": "BOT4",
        "dst_offset": 0,
    },
    {
        "index": 26,
        "zone_str": "(UTC-04:00) Santiago",
        "tz_str": "AMT4AMST,M10.3.0/0,M2.3.0/0",
        "dst_offset": 60,
    },
    {
        "index": 27,
        "zone_str": "(UTC-03:30) Newfoundland",
        "tz_str": "NST3:30NDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 28,
        "zone_str": "(UTC-03:00) Brasilia",
        "tz_str": "BRT3BRST,M10.3.0/0,M2.3.0/0",
        "dst_offset": 60,
    },
    {
        "index": 29,
        "zone_str": "(UTC-03:00) Buenos Aires",
        "tz_str": "<GMT+3>3",
        "dst_offset": 0,
    },
    {
        "index": 30,
        "zone_str": "(UTC-03:00) Cayenne, Fortaleza",
        "tz_str": "<GMT+3>3",
        "dst_offset": 0,
    },
    {
        "index": 31,
        "zone_str": "(UTC-03:00) Greenland",
        "tz_str": "PMST3PMDT,M3.2.0,M11.1.0",
        "dst_offset": 60,
    },
    {
        "index": 32,
        "zone_str": "(UTC-03:00) Montevideo",
        "tz_str": "UYT3UYST,M10.1.0,M3.2.0",
        "dst_offset": 60,
    },
    {
        "index": 33,
        "zone_str": "(UTC-03:00) Salvador",
        "tz_str": "<GMT+3>3",
        "dst_offset": 0,
    },
    {
        "index": 34,
        "zone_str": "(UTC-02:00) Coordinated Universal Time-02",
        "tz_str": "<GMT+2>2",
        "dst_offset": 0,
    },
    {
        "index": 35,
        "zone_str": "(UTC-01:00) Azores",
        "tz_str": "AZOT1AZOST,M3.5.0/0,M10.5.0/1",
        "dst_offset": 60,
    },
    {
        "index": 36,
        "zone_str": "(UTC-01:00) Cabo Verde Is.",
        "tz_str": "CVT1",
        "dst_offset": 0,
    },
    {
        "index": 37,
        "zone_str": "(UTC) Casablanca",
        "tz_str": "WET0WEST,M3.5.0,M10.5.0/3",
        "dst_offset": 60,
    },
    {
        "index": 38,
        "zone_str": "(UTC) Coordinated Universal Time",
        "tz_str": "GMT0",
        "dst_offset": 0,
    },
    {
        "index": 39,
        "zone_str": "(UTC) Dublin, Edinburgh, Lisbon, London",
        "tz_str": "GMT0BST,M3.5.0/1,M10.5.0",
        "dst_offset": 60,
    },
    {
        "index": 40,
        "zone_str": "(UTC) Monrovia, Reykjavik",
        "tz_str": "GMT0",
        "dst_offset": 0,
    },
    {
        "index": 41,
        "zone_str": "(UTC+01:00) Amsterdam, Berlin, Bern, Rome, Stockholm, Vienna",
        "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
        "dst_offset": 60,
    },
    {
        "index": 42,
        "zone_str": "(UTC+01:00) Belgrade, Bratislava, Budapest, Ljubljana, Prague",
        "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
        "dst_offset": 60,
    },
    {
        "index": 43,
        "zone_str": "(UTC+01:00) Brussels, Copenhagen, Madrid, Paris",
        "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
        "dst_offset": 60,
    },
    {
        "index": 44,
        "zone_str": "(UTC+01:00) Sarajevo, Skopje, Warsaw, Zagreb",
        "tz_str": "CET-1CEST,M3.5.0,M10.5.0/3",
        "dst_offset": 60,
    },
    {
        "index": 45,
        "zone_str": "(UTC+01:00) West Central Africa",
        "tz_str": "WAT-1",
        "dst_offset": 0,
    },
    {
        "index": 46,
        "zone_str": "(UTC+01:00) Windhoek",
        "tz_str": "WAT-1WAST,M9.1.0,M4.1.0",
        "dst_offset": 60,
    },
    {
        "index": 47,
        "zone_str": "(UTC+02:00) Amman",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 48,
        "zone_str": "(UTC+02:00) Athens, Bucharest",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 49,
        "zone_str": "(UTC+02:00) Beirut",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 50,
        "zone_str": "(UTC+02:00) Cairo",
        "tz_str": "<GMT-2>-2",
        "dst_offset": 0,
    },
    {
        "index": 51,
        "zone_str": "(UTC+02:00) Damascus",
        "tz_str": "EET-2EEST,M3.5.5/0,M10.5.5/0",
        "dst_offset": 60,
    },
    {
        "index": 52,
        "zone_str": "(UTC+02:00) E. Europe",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 53,
        "zone_str": "(UTC+02:00) Harare, Pretoria",
        "tz_str": "<GMT-2>-2",
        "dst_offset": 0,
    },
    {
        "index": 54,
        "zone_str": "(UTC+02:00) Helsinki, Kyiv, Riga, Sofia, Tallinn, Vilnius",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 55,
        "zone_str": "(UTC+02:00) Istanbul",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 56,
        "zone_str": "(UTC+02:00) Jerusalem",
        "tz_str": "EET-2EEST,M3.5.0/3,M10.5.0/4",
        "dst_offset": 60,
    },
    {
        "index": 57,
        "zone_str": "(UTC+02:00) Kaliningrad (RTZ 1)",
        "tz_str": "EET-2",
        "dst_offset": 0,
    },
    {
        "index": 58,
        "zone_str": "(UTC+02:00) Tripoli",
        "tz_str": "<GMT-2>-2",
        "dst_offset": 0,
    },
    {
        "index": 59,
        "zone_str": "(UTC+03:00) Baghdad",
        "tz_str": "AST-3",
        "dst_offset": 0,
    },
    {
        "index": 60,
        "zone_str": "(UTC+03:00) Kuwait, Riyadh",
        "tz_str": "AST-3",
        "dst_offset": 0,
    },
    {
        "index": 61,
        "zone_str": "(UTC+03:00) Minsk",
        "tz_str": "MSK-3",
        "dst_offset": 0,
    },
    {
        "index": 62,
        "zone_str": "(UTC+03:00) Moscow, St. Petersburg, Volgograd (RTZ 2)",
        "tz_str": "MSK-3",
        "dst_offset": 0,
    },
    {
        "index": 63,
        "zone_str": "(UTC+03:00) Nairobi",
        "tz_str": "<GMT-3>-3",
        "dst_offset": 0,
    },
    {
        "index": 64,
        "zone_str": "(UTC+03:30) Tehran",
        "tz_str": "AZT-3:30AZST,M3.5.0/4,M10.5.0/5",
        "dst_offset": 60,
    },
    {
        "index": 65,
        "zone_str": "(UTC+04:00) Abu Dhabi, Muscat",
        "tz_str": "GST-4",
        "dst_offset": 0,
    },
    {
        "index": 66,
        "zone_str": "(UTC+04:00) Baku",
        "tz_str": "AZT-4AZST,M3.5.0/4,M10.5.0/5",
        "dst_offset": 60,
    },
    {
        "index": 67,
        "zone_str": "(UTC+04:00) Izhevsk, Samara (RTZ 3)",
        "tz_str": "SAMT-4",
        "dst_offset": 0,
    },
    {
        "index": 68,
        "zone_str": "(UTC+04:00) Port Louis",
        "tz_str": "<GMT-4>-4",
        "dst_offset": 0,
    },
    {
        "index": 69,
        "zone_str": "(UTC+04:00) Tbilisi",
        "tz_str": "GET-4",
        "dst_offset": 0,
    },
    {
        "index": 70,
        "zone_str": "(UTC+04:00) Yerevan",
        "tz_str": "AMT-4",
        "dst_offset": 0,
    },
    {
        "index": 71,
        "zone_str": "(UTC+04:30) Kabul",
        "tz_str": "AFT-4:30",
        "dst_offset": 0,
    },
    {
        "index": 72,
        "zone_str": "(UTC+05:00) Ashgabat, Tashkent",
        "tz_str": "TMT-5",
        "dst_offset": 0,
    },
    {
        "index": 73,
        "zone_str": "(UTC+05:00) Ekaterinburg (RTZ 4)",
        "tz_str": "YEKT-5",
        "dst_offset": 0,
    },
    {
        "index": 74,
        "zone_str": "(UTC+05:00) Islamabad, Karachi",
        "tz_str": "PKT-5",
        "dst_offset": 0,
    },
    {
        "index": 75,
        "zone_str": "(UTC+05:30) Chennai, Kolkata, Mumbai, New Delhi",
        "tz_str": "IST-5:30",
        "dst_offset": 0,
    },
    {
        "index": 76,
        "zone_str": "(UTC+05:30) Sri Jayawardenepura",
        "tz_str": "IST-5:30",
        "dst_offset": 0,
    },
    {
        "index": 77,
        "zone_str": "(UTC+05:45) Kathmandu",
        "tz_str": "NPT-5:45",
        "dst_offset": 0,
    },
    {
        "index": 78,
        "zone_str": "(UTC+06:00) Astana",
        "tz_str": "<GMT-6>-6",
        "dst_offset": 0,
    },
    {
        "index": 79,
        "zone_str": "(UTC+06:00) Dhaka",
        "tz_str": "BDT-6",
        "dst_offset": 0,
    },
    {
        "index": 80,
        "zone_str": "(UTC+06:00) Novosibirsk (RTZ 5)",
        "tz_str": "NOVT-6",
        "dst_offset": 0,
    },
    {
        "index": 81,
        "zone_str": "(UTC+06:30) Yangon (Rangoon)",
        "tz_str": "MMT-6:30",
        "dst_offset": 0,
    },
    {
        "index": 82,
        "zone_str": "(UTC+07:00) Bangkok, Hanoi, Jakarta",
        "tz_str": "ICT-7",
        "dst_offset": 0,
    },
    {
        "index": 83,
        "zone_str": "(UTC+07:00) Krasnoyarsk (RTZ 6)",
        "tz_str": "KRAT-7",
        "dst_offset": 0,
    },
    {
        "index": 84,
        "zone_str": "(UTC+08:00) Beijing, Chongqing, Hong Kong, Urumqi",
        "tz_str": "CST-8",
        "dst_offset": 0,
    },
    {
        "index": 85,
        "zone_str": "(UTC+08:00) Irkutsk (RTZ 7)",
        "tz_str": "IRKT-8",
        "dst_offset": 0,
    },
    {
        "index": 86,
        "zone_str": "(UTC+08:00) Kuala Lumpur, Singapore",
        "tz_str": "MYT-8",
        "dst_offset": 0,
    },
    {
        "index": 87,
        "zone_str": "(UTC+08:00) Perth",
        "tz_str": "<GMT-8>-8",
        "dst_offset": 0,
    },
    {
        "index": 88,
        "zone_str": "(UTC+08:00) Taipei",
        "tz_str": "CST-8",
        "dst_offset": 0,
    },
    {
        "index": 89,
        "zone_str": "(UTC+08:00) Ulaanbaatar",
        "tz_str": "<GMT-8>-8",
        "dst_offset": 0,
    },
    {
        "index": 90,
        "zone_str": "(UTC+09:00) Osaka, Sapporo, Tokyo",
        "tz_str": "JST-9",
        "dst_offset": 0,
    },
    {
        "index": 91,
        "zone_str": "(UTC+09:00) Seoul",
        "tz_str": "KST-9",
        "dst_offset": 0,
    },
    {
        "index": 92,
        "zone_str": "(UTC+09:00) Yakutsk (RTZ 8)",
        "tz_str": "YAKT-9",
        "dst_offset": 0,
    },
    {
        "index": 93,
        "zone_str": "(UTC+09:30) Adelaide",
        "tz_str": "ACST-9:30ACDT,M10.1.0,M4.1.0/3",
        "dst_offset": 60,
    },
    {
        "index": 94,
        "zone_str": "(UTC+09:30) Darwin",
        "tz_str": "ACST-9:30",
        "dst_offset": 0,
    },
    {
        "index": 95,
        "zone_str": "(UTC+10:00) Brisbane",
        "tz_str": "<GMT-10>-10",
        "dst_offset": 0,
    },
    {
        "index": 96,
        "zone_str": "(UTC+10:00) Canberra, Melbourne, Sydney",
        "tz_str": "AEST-10AEDT,M10.1.0,M4.1.0/3",
        "dst_offset": 60,
    },
    {
        "index": 97,
        "zone_str": "(UTC+10:00) Guam, Port Moresby",
        "tz_str": "ChST-10",
        "dst_offset": 0,
    },
    {
        "index": 98,
        "zone_str": "(UTC+10:00) Hobart",
        "tz_str": "AEST-10AEDT,M10.1.0,M4.1.0/3",
        "dst_offset": 60,
    },
    {
        "index": 99,
        "zone_str": "(UTC+10:00) Magadan",
        "tz_str": "MAGT-10",
        "dst_offset": 0,
    },
    {
        "index": 100,
        "zone_str": "(UTC+10:00) Vladivostok, Magadan (RTZ 9)",
        "tz_str": "VLAT-10",
        "dst_offset": 0,
    },
    {
        "index": 101,
        "zone_str": "(UTC+11:00) Chokurdakh (RTZ 10)",
        "tz_str": "<GMT-11>-11",
        "dst_offset": 0,
    },
    {
        "index": 102,
        "zone_str": "(UTC+11:00) Solomon Is., New Caledonia",
        "tz_str": "SBT-11",
        "dst_offset": 0,
    },
    {
        "index": 103,
        "zone_str": "(UTC+12:00) Anadyr, Petropavlovsk-Kamchatsky (RTZ 11)",
        "tz_str": "ANAT-12",
        "dst_offset": 0,
    },
    {
        "index": 104,
        "zone_str": "(UTC+12:00) Auckland, Wellington",
        "tz_str": "NZST-12NZDT,M9.5.0,M4.1.0/3",
        "dst_offset": 60,
    },
    {
        "index": 105,
        "zone_str": "(UTC+12:00) Coordinated Universal Time+12",
        "tz_str": "<GMT-12>-12",
        "dst_offset": 0,
    },
    {
        "index": 106,
        "zone_str": "(UTC+12:00) Fiji",
        "tz_str": "NZST-12NZDT,M9.5.0,M4.1.0/3",
        "dst_offset": 60,
    },
    {
        "index": 107,
        "zone_str": "(UTC+13:00) Nuku'alofa",
        "tz_str": "TKT-13",
        "dst_offset": 0,
    },
    {
        "index": 108,
        "zone_str": "(UTC+13:00) Samoa",
        "tz_str": "WSST-13WSDT,M9.5.0/3,M4.1.0/4",
        "dst_offset": 60,
    },
    {
        "index": 109,
        "zone_str": "(UTC+14:00) Kiritimati Island",
        "tz_str": "LINT-14",
        "dst_offset": 0,
    },
]


class Time(Module):
    """Implements the timezone settings."""

    def query(self):
        """Request time and timezone."""
        q = self.query_for_command("get_time")

        merge(q, self.query_for_command("get_timezone"))
        return q

    @property
    def time(self) -> datetime:
        """Return current device time."""
        res = self.data["get_time"]
        return datetime(
            res["year"],
            res["month"],
            res["mday"],
            res["hour"],
            res["min"],
            res["sec"],
        )

    @property
    def timezone(self):
        """Return current timezone."""
        res = self.data["get_timezone"]
        return res

    async def get_time(self):
        """Return current device time."""
        try:
            res = await self.call("get_time")
            return datetime(
                res["year"],
                res["month"],
                res["mday"],
                res["hour"],
                res["min"],
                res["sec"],
            )
        except SmartDeviceException:
            return None

    async def get_timezone(self):
        """Request timezone information from the device."""
        return await self.call("get_timezone")

    def get_timezones(self):
        """Return allowed timezones."""
        return timezones

    async def set_timezone(self, tz_index):
        """Request timezone information from the device."""
        return await self.call("set_timezone", {"index": tz_index})
