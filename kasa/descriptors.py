"""Generic interface for defining device features."""
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable


class DescriptorCategory(Enum):
    """Descriptor category."""

    # TODO: we could probably do better than using the scheme homeassistant is using
    Config = auto()
    Diagnostic = auto()


class DescriptorType(Enum):
    """Type of the information defined by the descriptor."""

    Sensor = auto()
    BinarySensor = auto()
    Switch = auto()
    Button = auto()


@dataclass
class Descriptor:
    """Descriptor defines a generic interface for device features."""

    device: Any  # TODO: rename to something else, this can also be a module.
    #: User-friendly short description
    name: str
    #: Name of the property that allows accessing the value
    attribute_getter: str | Callable
    #: Name of the method that allows changing the value
    attribute_setter: str | None = None
    #: Type of the information
    icon: str | None = None
    #: Unit of the descriptor
    unit: str | None = None
    #: Hint for homeassistant
    #: TODO: Replace with a set of flags to allow homeassistant make its own decision?
    show_in_hass: bool = True
    category: DescriptorCategory = DescriptorCategory.Diagnostic
    type: DescriptorType = DescriptorType.Sensor

    @property
    def value(self):
        """Return the current value."""
        if isinstance(self.attribute_getter, Callable):
            return self.attribute_getter(self.device)
        return getattr(self.device, self.attribute_getter)

    async def set_value(self, value):
        """Set the value."""
        return await getattr(self.device, self.attribute_setter)(value)
