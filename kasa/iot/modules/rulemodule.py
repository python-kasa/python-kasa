"""Base implementation for all rule-based modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Generic, TypeVar

from mashumaro import DataClassDictMixin

from ..iotmodule import IotModule, merge


class Action(Enum):
    """Action to perform."""

    Disabled = -1
    TurnOff = 0
    TurnOn = 1
    Unknown = 2


class TimeOption(Enum):
    """Time when the action is executed."""

    Disabled = -1
    Enabled = 0
    AtSunrise = 1
    AtSunset = 2


@dataclass
class Rule(DataClassDictMixin):
    """Representation of a schedule or anti-theft rule.

    ``wday`` has one flag per weekday, starting on Sunday.
    ``smin`` and ``emin`` are minutes after midnight. For sunrise and sunset
    rules the device fills in today's time itself.
    """

    id: str
    name: str
    enable: int
    wday: list[int]
    repeat: int

    # start action
    sact: Action | None = None
    stime_opt: TimeOption | None = None
    smin: int | None = None
    soffset: int | None = None

    eact: Action | None = None
    etime_opt: TimeOption | None = None
    emin: int | None = None
    eoffset: int | None = None

    # Only on anti-theft rules
    frequency: int | None = None

    # Only on bulbs
    s_light: dict | None = None


@dataclass
class CountdownRule(DataClassDictMixin):
    """Representation of a countdown rule.

    The device performs ``act`` once ``delay`` seconds after the rule is
    enabled, then disables the rule. ``remain`` is the number of seconds left.
    """

    id: str
    name: str
    enable: int
    delay: int
    act: Action
    remain: int | None = None


RuleT = TypeVar("RuleT", Rule, CountdownRule)

_LOGGER = logging.getLogger(__name__)


class RuleModule(IotModule, Generic[RuleT]):
    """Base class for rule-based modules, such as countdown and antitheft."""

    _rule_class: type[RuleT]

    def query(self) -> dict:
        """Prepare the query for rules."""
        q = self.query_for_command("get_rules")
        return merge(q, self.query_for_command("get_next_action"))

    @property
    def rules(self) -> list[RuleT]:
        """Return the list of rules for the service."""
        try:
            return [
                self._rule_class.from_dict(rule)
                for rule in self.data["get_rules"]["rule_list"]
            ]
        except Exception as ex:
            _LOGGER.error("Unable to read rule list: %s (data: %s)", ex, self.data)
            return []

    @property
    def enabled(self) -> bool:
        """Return True if the service is enabled as a whole."""
        return bool(self.data["get_rules"].get("enable"))

    async def set_enabled(self, state: bool) -> dict:
        """Enable or disable the service."""
        return await self.call("set_overall_enable", {"enable": int(state)})

    async def add_rule(self, rule: RuleT) -> dict:
        """Add a rule. The id of the given rule is ignored.

        Returns the device response, which contains the id of the new rule.
        """
        return await self.call("add_rule", self._rule_params(rule))

    async def edit_rule(self, rule: RuleT) -> dict:
        """Replace the rule that has the same id with the given rule."""
        return await self.call("edit_rule", {"id": rule.id, **self._rule_params(rule)})

    async def set_rule_enabled(self, rule: RuleT, state: bool) -> dict:
        """Enable or disable a single rule."""
        return await self.edit_rule(replace(rule, enable=int(state)))

    async def delete_rule(self, rule: RuleT) -> dict:
        """Delete the given rule."""
        return await self.call("delete_rule", {"id": rule.id})

    async def delete_all_rules(self) -> dict:
        """Delete all rules."""
        return await self.call("delete_all_rules")

    def _rule_params(self, rule: RuleT) -> dict[str, Any]:
        """Return the parameters for adding or editing a rule."""
        params = {k: v for k, v in rule.to_dict().items() if v is not None}
        params.pop("id")
        params.pop("remain", None)  # read-only countdown state
        if isinstance(rule, Rule):
            # Rules are listed without their unused end action, but adding or
            # editing a rule without it fails with "invalid argument".
            params.setdefault("eact", Action.Disabled.value)
            params.setdefault("etime_opt", TimeOption.Disabled.value)
            params.setdefault("emin", 0)
        return params
