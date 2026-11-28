"""Schedule module implementation."""

from __future__ import annotations

from datetime import datetime, timedelta

from ...device_type import DeviceType
from ...feature import Feature
from .rulemodule import Action, Rule, RuleModule


class Schedule(RuleModule[Rule]):
    """Implements the scheduling interface."""

    _rule_class = Rule

    def _initialize_features(self) -> None:
        """Initialize features after the initial update."""
        # Strip sockets keep their own rules; without a socket context the
        # strip only mirrors the first socket, so expose features per socket.
        if self._device.device_type is DeviceType.Strip:
            return

        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="schedule_enabled",
                name="Schedule enabled",
                icon="mdi:calendar-clock",
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                type=Feature.Type.Switch,
                category=Feature.Category.Config,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="next_schedule_time",
                name="Next scheduled action time",
                icon="mdi:calendar-clock",
                attribute_getter="next_action_time",
                type=Feature.Type.Sensor,
                category=Feature.Category.Info,
            )
        )
        self._add_feature(
            Feature(
                device=self._device,
                container=self,
                id="next_schedule_action",
                name="Next scheduled action",
                icon="mdi:calendar-clock",
                attribute_getter="next_action_state",
                type=Feature.Type.Sensor,
                category=Feature.Category.Info,
            )
        )

    @property
    def _next_action(self) -> dict:
        """Return the next action for today, or an empty dict if there is none."""
        next_action = self.data.get("get_next_action", {})
        if next_action.get("type", -1) == -1 or "schd_time" not in next_action:
            return {}
        return next_action

    @property
    def next_action(self) -> Action | None:
        """Return the next scheduled action for today."""
        if not (next_action := self._next_action):
            return None
        return Action(next_action["action"])

    @property
    def next_action_state(self) -> str | None:
        """Return the state the next scheduled action sets: 'on' or 'off'."""
        if (action := self.next_action) is Action.TurnOn:
            return "on"
        if action is Action.TurnOff:
            return "off"
        return None

    @property
    def next_action_time(self) -> datetime | None:
        """Return when the next scheduled action for today happens.

        The device reports it as seconds after midnight, local device time.
        """
        if not (next_action := self._next_action):
            return None
        midnight = self._device.time.replace(hour=0, minute=0, second=0, microsecond=0)
        return midnight + timedelta(seconds=next_action["schd_time"])
