"""Package for interfaces."""

from .fan import Fan
from .led import Led
from .light import Light, LightPreset
from .lighteffect import LightEffect

__all__ = [
    "Fan",
    "Led",
    "Light",
    "LightEffect",
    "LightPreset",
]
