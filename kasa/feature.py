"""Generic interface for defining device features."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .device import Device


_LOGGER = logging.getLogger(__name__)


@dataclass
class HassCompat:
    """Container class for homeassistant compat.

    This is used to define some metadata for homeassistant for better UX.
    This can be directly passed to *Description constructors.
    """

    class DeviceClass(Enum):
        """Device class for homeassistant compat.

        This contains only classes used in this library.
        """

        # Sensor
        Power = "power"  # W, kW
        Energy = "energy"  # wH, kWh
        Battery = "battery"  # %
        Voltage = "voltage"  # V, mV
        Current = "current"  # A, mA
        Humidity = "humidity"  # %
        Temperature = "temperature"  # ⁰C, ⁰F, K
        Timestamp = "timestamp"  # ISO8601

        # Binary sensor
        LowBattery = "battery"
        Connected = "connectivity"
        # TODO: We don't want duplicate opened state, which one to use?
        DoorOpen = "door"
        WindowOpen = "window"
        Overheated = "heat"
        Wet = "moisture"
        Problem = "problem"
        UpdateAvailable = "update"

        def __str__(self):
            """Overridden to return only the value."""
            return self.value

    class StateClass(Enum):
        """State class compat for homeassistant."""

        Measurement = "measurement"
        Total = "total"
        TotalIncreasing = "total_increasing"

        def __str__(self):
            """Overridden to return only the value."""
            return self.value

    device_class: DeviceClass | None = None
    state_class: StateClass | None = None
    entity_registry_enabled_default: bool = True
    entity_registry_visible_default: bool = True

    def dict(self):
        """Convert to dict ready to consume by homeassistant description classes."""
        items = asdict(self).items()
        return {k: v for k, v in items if v is not None}


@dataclass
class Feature:
    """Feature defines a generic interface for device features."""

    class Type(Enum):
        """Type to help decide how to present the feature."""

        #: Sensor is an informative read-only value
        Sensor = auto()
        #: BinarySensor is a read-only boolean
        BinarySensor = auto()
        #: Switch is a boolean setting
        Switch = auto()
        #: Action triggers some action on device
        Action = auto()
        #: Number defines a numeric setting
        #: See :ref:`range_getter`, :ref:`minimum_value`, and :ref:`maximum_value`
        Number = auto()
        #: Choice defines a setting with pre-defined values
        Choice = auto()
        Unknown = -1

    # TODO: unsure if this is a great idea..
    Sensor = Type.Sensor
    BinarySensor = Type.BinarySensor
    Switch = Type.Switch
    Action = Type.Action
    Number = Type.Number
    Choice = Type.Choice

    class Category(Enum):
        """Category hint to allow feature grouping."""

        #: Primary features control the device state directly.
        #: Examples include turning the device on/off, or adjusting its brightness.
        Primary = auto()
        #: Config features change device behavior without immediate state changes.
        Config = auto()
        #: Informative/sensor features deliver some potentially interesting information.
        Info = auto()
        #: Debug features deliver more verbose information then informative features.
        #: You may want to hide these per default to avoid cluttering your UI.
        Debug = auto()
        #: The default category if none is specified.
        Unset = -1

    #: Device instance required for getting and setting values
    device: Device
    #: User-friendly short description
    name: str
    #: Name of the property that allows accessing the value
    attribute_getter: str | Callable | None = None
    #: Name of the method that allows changing the value
    attribute_setter: str | None = None
    #: Container storing the data, this overrides 'device' for getters
    container: Any = None
    #: Icon suggestion
    icon: str | None = None
    #: Unit, if applicable
    unit: str | None = None
    #: Category hint for downstreams
    category: Feature.Category = Category.Unset
    #: Type of the feature
    type: Feature.Type = Type.Sensor

    # Number-specific attributes
    #: Minimum value
    minimum_value: int = 0
    #: Maximum value
    maximum_value: int = 2**16  # Arbitrary max
    #: Attribute containing the name of the range getter property.
    #: If set, this property will be used to set *minimum_value* and *maximum_value*.
    range_getter: str | None = None

    #: Homeassistant compat
    hass_compat: HassCompat | None = None

    #: Identifier
    id: str | None = None

    def __post_init__(self):
        """Handle late-binding of members."""
        # Set id, if unset
        if self.id is None:
            self.id = self.name.lower().replace(" ", "_")

        # Populate minimum & maximum values, if range_getter is given
        container = self.container if self.container is not None else self.device
        if self.range_getter is not None:
            self.minimum_value, self.maximum_value = getattr(
                container, self.range_getter
            )

        # Set the category, if unset
        if self.category is Feature.Category.Unset:
            if self.attribute_setter:
                self.category = Feature.Category.Config
            else:
                self.category = Feature.Category.Info

        if self.category == Feature.Category.Config and self.type in [
            Feature.Type.Sensor,
            Feature.Type.BinarySensor,
        ]:
            raise ValueError(
                f"Invalid type for configurable feature: {self.name} ({self.id}):"
                f" {self.type}"
            )

        if self.hass_compat is None:
            self.hass_compat = HassCompat()

    @property
    def value(self):
        """Return the current value."""
        if self.type == Feature.Type.Action:
            return "<Action>"
        if self.attribute_getter is None:
            raise ValueError("Not an action and no attribute_getter set")

        container = self.container if self.container is not None else self.device
        if isinstance(self.attribute_getter, Callable):
            return self.attribute_getter(container)
        return getattr(container, self.attribute_getter)

    async def set_value(self, value):
        """Set the value."""
        if self.attribute_setter is None:
            raise ValueError("Tried to set read-only feature.")
        if self.type == Feature.Type.Number:  # noqa: SIM102
            if value < self.minimum_value or value > self.maximum_value:
                raise ValueError(
                    f"Value {value} out of range "
                    f"[{self.minimum_value}, {self.maximum_value}]"
                )

        container = self.container if self.container is not None else self.device
        if self.type == Feature.Type.Action:
            return await getattr(container, self.attribute_setter)()

        return await getattr(container, self.attribute_setter)(value)

    def __repr__(self):
        s = f"{self.name} ({self.id}): {self.value}"
        if self.unit is not None:
            s += f" {self.unit}"

        if self.type == Feature.Type.Number:
            s += f" (range: {self.minimum_value}-{self.maximum_value})"

        return s
