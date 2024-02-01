from ..smartmodule import SmartModule
from pydantic import BaseModel, Field
from enum import Enum

class Type(Enum):
    Last = "last_states"
    Custom = "custom"


class DefaultStatesModel(BaseModel):
    type = Field()
    state = Field()  # if type is custom, something like {"state": {"on": False}}
    """l530:
    "state": {
146-                "brightness": 100,
147-                "color_temp": 9000,
148-                "hue": 0,
149-                "saturation": 100
150-            },

    """

"""L510, type stored inside brightness:
"brightness": {
126-                "type": "last_states",
127-                "value": 100
128-            },


"""
    re_power_type = Field()  # seen on L530, "re_power_type": "always_on", KS225 "always_off"
    re_power_type_capability: list | None  # KS225: ["last_states", "always_on", "always_off"]

class DefaultStates(SmartModule):
    QUERY_GETTER_NAME = None
    REQUIRED_COMPONENT = "default_states"
