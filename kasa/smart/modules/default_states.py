from enum import Enum

from pydantic import BaseModel, Field

from ..smartmodule import SmartModule


class Type(Enum):
    Last = "last_states"
    Custom = "custom"


class DefaultStatesModel(BaseModel):
    type = Field()
    state = Field()  # if type is custom, something like {"state": {"on": False}}
    """l530:
    {"state": {
      "brightness": 100,
      "color_temp": 9000,
      "hue": 0,
      "saturation": 100
      }
    }
    """

    """L510, type stored inside brightness:
    {"brightness": {
      "type": "last_states",
      "value": 100
      }
    }
    """
    re_power_type = (
        Field()
    )  # seen on L530, "re_power_type": "always_on", KS225 "always_off"
    re_power_type_capability: list | None  # KS225: ["last_states", "always_on", "always_off"]


class DefaultStates(SmartModule):
    QUERY_GETTER_NAME = None
    REQUIRED_COMPONENT = "default_states"
